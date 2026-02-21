from django import template

register = template.Library()

@register.filter
def get_item(d, key):
    if d is None:
        return None
    return d.get(key)


@register.filter
def message_bootstrap_class(tags):
    """Map Django message tags to Bootstrap 5 alert classes."""
    if tags == "error":
        return "danger"
    return tags or "info"

@register.simple_tag
def pred_for(predictions_map, user_id, event_id):
    return predictions_map.get((user_id, event_id))

@register.simple_tag
def score_for(scores_map, user_id, event_id):
    return scores_map.get((user_id, event_id))