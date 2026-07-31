const ALLOWED_METHODS = new Set(["getMe", "getUpdates", "sendMessage"]);

export default {
  async fetch(request, env) {
    if (!env.TELEGRAM_BOT_TOKEN || !env.PROXY_SECRET) {
      return new Response("Worker secrets are not configured", { status: 500 });
    }

    if (
      request.method !== "POST" ||
      request.headers.get("X-Proxy-Secret") !== env.PROXY_SECRET
    ) {
      return new Response("Forbidden", { status: 403 });
    }

    const method = new URL(request.url).pathname.replace(/^\/+|\/+$/g, "");
    if (!ALLOWED_METHODS.has(method)) {
      return new Response("Not found", { status: 404 });
    }

    const telegramResponse = await fetch(
      `https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/${method}`,
      {
        method: "POST",
        headers: {
          "Content-Type":
            request.headers.get("Content-Type") ||
            "application/x-www-form-urlencoded",
        },
        body: await request.arrayBuffer(),
      },
    );

    return new Response(telegramResponse.body, {
      status: telegramResponse.status,
      headers: {
        "Content-Type":
          telegramResponse.headers.get("Content-Type") || "application/json",
        "Cache-Control": "no-store",
      },
    });
  },
};
