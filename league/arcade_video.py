"""Best-run video uploads to the existing S3 bucket, without assembling files on the app disk."""
import json
import logging
import uuid
from datetime import timedelta
from functools import wraps

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.files.storage import default_storage
from django.db import transaction
from django.http import JsonResponse, Http404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import arcade_library as library
from .models import ArcadeBestVideo, ArcadeVideoUpload

log = logging.getLogger(__name__)
PART_SIZE = 5 * 1024 * 1024
MAX_SIZE = 1024 * 1024 * 1024
MAX_DURATION = 5 * 60 * 60 * 1000


class VideoRejected(ValueError):
    pass


def enabled():
    return bool(getattr(settings, "USE_S3", False))


def config(request, game_key, admin_test=False):
    if not enabled() or not request.user.is_authenticated or admin_test:
        return None
    return {"game":game_key, "initUrl":reverse("league:arcade_video_init"),
            "partSize":PART_SIZE, "maxSize":MAX_SIZE}


def s3():
    if not enabled():
        raise VideoRejected("Видеохранилище не подключено.")
    storage = default_storage
    return storage.connection.meta.client, storage.bucket_name


def storage_key(name):
    return "/".join(part for part in (getattr(default_storage, "location", "").strip("/"), name) if part)


def current_attempt(user, game, attempt_id, *, lock_record=False):
    if game not in {"flappy", "doodle_jump", "tetris"}:
        raise VideoRejected("Игра не поддерживает видеозапись.")
    Attempt, Record = library.models_for(game)
    records = Record.objects.select_for_update() if lock_record else Record.objects
    record = records.filter(user=user).first()
    attempt = Attempt.objects.filter(user=user, pk=attempt_id, is_excluded=False, is_manual=False,
        finished_at__isnull=False, score__isnull=False).first()
    if not record or not attempt or attempt.score != record.best_score or attempt.score <= 0:
        raise VideoRejected("Попытка не является текущим личным рекордом.")
    first = Attempt.objects.filter(user=user, is_excluded=False, score=record.best_score,
        finished_at__isnull=False).order_by("finished_at", "pk").values_list("pk", flat=True).first()
    if first != attempt.pk:
        raise VideoRejected("Этот результат не улучшил предыдущий рекорд.")
    return attempt


def api(view):
    @login_required
    @require_POST
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        try:
            limit = PART_SIZE+65536 if view.__name__ == "part" else 8192
            if int(request.META.get("CONTENT_LENGTH") or 0) > limit:
                return JsonResponse({"error":"Слишком большой фрагмент видео."}, status=413)
            return view(request, *args, **kwargs)
        except VideoRejected as error:
            return JsonResponse({"error":str(error)}, status=409)
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            return JsonResponse({"error":"Некорректные данные видео."}, status=400)
        except Http404:
            raise
        except Exception:
            log.exception("Arcade video storage operation failed")
            return JsonResponse({"error":"Не удалось сохранить видео. Результат игры сохранён отдельно."}, status=503)
    return wrapped


def payload(request):
    data = json.loads(request.body)
    if not isinstance(data, dict):
        raise ValueError
    return data


def abort(upload):
    client, bucket = s3()
    try:
        client.abort_multipart_upload(Bucket=bucket, Key=storage_key(upload.file_name), UploadId=upload.upload_id)
    except Exception as error:
        if getattr(error, "response", {}).get("Error", {}).get("Code") != "NoSuchUpload":
            raise


@api
@transaction.atomic
def initialize(request):
    data = payload(request)
    game, attempt_id, mime = data.get("game"), data.get("attempt_id"), data.get("mime")
    size, duration = data.get("size"), data.get("duration_ms")
    if (type(attempt_id) is not int or type(size) is not int or not 1 <= size <= MAX_SIZE
            or type(duration) is not int or not 1 <= duration <= MAX_DURATION or mime not in ("video/mp4","video/webm")):
        raise ValueError
    current_attempt(request.user, game, attempt_id)
    User.objects.select_for_update().get(pk=request.user.pk)
    current_attempt(request.user, game, attempt_id)
    existing = ArcadeVideoUpload.objects.filter(user=request.user, game_key=game, attempt_id=attempt_id,
        aborted_at__isnull=True, created_at__gte=timezone.now()-timedelta(hours=24)).order_by("-created_at").first()
    if existing:
        if (existing.size, existing.mime, existing.duration_ms) != (size, mime, duration):
            raise VideoRejected("Параметры записи изменились.")
        return upload_response(existing)
    # Bound abandoned multipart sessions per player/game; the cleanup command
    # handles closed tabs and expired sessions as well.
    for old in ArcadeVideoUpload.objects.select_for_update().filter(user=request.user, game_key=game,
            completed_at__isnull=True, aborted_at__isnull=True):
        abort(old)
        old.aborted_at = timezone.now()
        old.save(update_fields=("aborted_at",))
    name = f"arcade-videos/{request.user.pk}/{game}/{uuid.uuid4().hex}.{'mp4' if mime == 'video/mp4' else 'webm'}"
    client, bucket = s3()
    upload_id = client.create_multipart_upload(Bucket=bucket, Key=storage_key(name), ContentType=mime)["UploadId"]
    try:
        upload = ArcadeVideoUpload.objects.create(user=request.user, game_key=game, attempt_id=attempt_id,
            file_name=name, upload_id=upload_id, mime=mime, size=size, duration_ms=duration)
    except Exception:
        client.abort_multipart_upload(Bucket=bucket, Key=storage_key(name), UploadId=upload_id)
        raise
    transaction.on_commit(lambda: cleanup(limit=1))
    return upload_response(upload)


def upload_response(upload):
    return JsonResponse({"id":str(upload.pk), "received":upload.received, "completed":bool(upload.completed_at),
        "part_url":reverse("league:arcade_video_part", args=[upload.pk]),
        "complete_url":reverse("league:arcade_video_complete", args=[upload.pk])})


def locked_upload(request, upload_id):
    upload = ArcadeVideoUpload.objects.select_for_update().filter(pk=upload_id, user=request.user).first()
    if upload is None:
        raise Http404
    if upload.aborted_at or upload.created_at < timezone.now()-timedelta(hours=24):
        raise VideoRejected("Время загрузки истекло.")
    return upload


@api
@transaction.atomic
def part(request, upload_id):
    upload = locked_upload(request, upload_id)
    if upload.completed_at:
        return JsonResponse({"received":upload.received})
    current_attempt(request.user, upload.game_key, upload.attempt_id)
    file = request.FILES.get("chunk")
    number = int(request.POST.get("part", "0"))
    if number < 1:
        raise ValueError
    if number <= len(upload.parts):
        return JsonResponse({"received":upload.received})  # Lost-response retry.
    if (not file or number != len(upload.parts)+1 or not 1 <= file.size <= PART_SIZE
            or upload.received+file.size > upload.size
            or (file.size != PART_SIZE and upload.received+file.size != upload.size)):
        raise ValueError
    if number == 1:
        header = file.read(16)
        file.seek(0)
        if not ((upload.mime == "video/webm" and header.startswith(b"\x1aE\xdf\xa3"))
                or (upload.mime == "video/mp4" and header[4:8] == b"ftyp")):
            raise ValueError
    client, bucket = s3()
    result = client.upload_part(Bucket=bucket, Key=storage_key(upload.file_name), UploadId=upload.upload_id,
        PartNumber=number, Body=file, ContentLength=file.size)
    upload.parts.append({"PartNumber":number, "ETag":result["ETag"]})
    upload.received += file.size
    upload.save(update_fields=("parts", "received"))
    return JsonResponse({"received":upload.received})


def delete_replaced(upload_id):
    upload = ArcadeVideoUpload.objects.filter(pk=upload_id).first()
    if not upload or not upload.delete_pending.startswith("arcade-videos/"):
        return
    try:
        default_storage.delete(upload.delete_pending)
        ArcadeVideoUpload.objects.filter(pk=upload_id).update(delete_pending="")
    except Exception:
        log.exception("Replaced arcade video deletion queued for retry")


@api
@transaction.atomic
def complete(request, upload_id):
    upload = locked_upload(request, upload_id)
    if upload.completed_at:
        return JsonResponse({"saved":True})
    attempt = current_attempt(request.user, upload.game_key, upload.attempt_id, lock_record=True)
    if upload.received != upload.size or not upload.parts:
        raise VideoRejected("Видео загружено не полностью. Предыдущая запись сохранена.")
    client, bucket = s3()
    # A retried completion may refer to an already assembled object (e.g. the
    # database connection failed after S3 completed the multipart upload).
    try:
        client.complete_multipart_upload(Bucket=bucket, Key=storage_key(upload.file_name), UploadId=upload.upload_id,
            MultipartUpload={"Parts":upload.parts})
    except Exception as error:
        if getattr(error, "response", {}).get("Error", {}).get("Code") != "NoSuchUpload":
            raise
    if client.head_object(Bucket=bucket, Key=storage_key(upload.file_name))["ContentLength"] != upload.size:
        raise VideoRejected("Размер видео не совпадает. Предыдущая запись сохранена.")
    old = ArcadeBestVideo.objects.filter(user=request.user, game_key=upload.game_key).first()
    upload.delete_pending = old.video.name if old and old.video.name != upload.file_name else ""
    ArcadeBestVideo.objects.update_or_create(user=request.user, game_key=upload.game_key, defaults={
        "attempt_id":attempt.pk, "score":attempt.score, "video":upload.file_name,
        "duration_ms":upload.duration_ms, "size":upload.size})
    upload.completed_at = timezone.now()
    upload.save(update_fields=("completed_at", "delete_pending"))
    transaction.on_commit(lambda: delete_replaced(upload.pk))
    return JsonResponse({"saved":True})


def cleanup(limit=None):
    expired = ArcadeVideoUpload.objects.filter(completed_at__isnull=True,
        created_at__lt=timezone.now()-timedelta(hours=24)).order_by("created_at")
    if limit is not None:
        expired = expired[:limit]
    for upload in expired:
        try:
            abort(upload)
            # Also handles a completed S3 object whose DB transaction rolled back.
            if upload.file_name.startswith("arcade-videos/") and not ArcadeBestVideo.objects.filter(video=upload.file_name).exists():
                default_storage.delete(upload.file_name)
            upload.delete()
        except Exception:
            log.exception("Expired arcade video upload cleanup failed")
    pending = ArcadeVideoUpload.objects.exclude(delete_pending="")
    if limit is not None:
        pending = pending[:limit]
    for upload in pending:
        delete_replaced(upload.pk)
    ArcadeVideoUpload.objects.filter(completed_at__lt=timezone.now()-timedelta(days=7), delete_pending="").delete()
