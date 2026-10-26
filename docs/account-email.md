# Accounts and recovery mail

New accounts have a public name (User.first_name), a unique lowercase handle
(UserProfile.handle), email and a confirmed password. Existing usernames and
passwords remain valid; existing public names do not change. Migration 0051
assigns safe handles to old accounts. Owners can see/change theirs in profile
→ Настройки аккаунта, and add their recovery address after verifying a password.

Configure these environment variables in Timeweb (do not commit credentials):

- EMAIL_HOST: the SMTP hostname supplied by the mailbox provider
- EMAIL_PORT: typically 587 (TLS) or 465 (SSL)
- EMAIL_HOST_USER: full mailbox address
- EMAIL_HOST_PASSWORD: mailbox SMTP/app password
- EMAIL_USE_TLS: True for port 587; False for SSL
- EMAIL_USE_SSL: True for port 465; False for TLS
- DEFAULT_FROM_EMAIL: Fastlap <your-mailbox@fastlap.ru>
- SITE_URL: https://fastlap.ru

TLS and SSL must not both be enabled. Use the provider's exact settings and
authorize the sender/domain (SPF/DKIM) as instructed by that provider.
EMAIL_BACKEND defaults to Django SMTP. Without EMAIL_HOST the recovery page
reports that mail is temporarily unavailable; it does not pretend to send.
For automated tests use django.core.mail.backends.locmem.EmailBackend.

Recovery links use SITE_URL rather than the request Host. Tokens expire after
one hour and become invalid after a successful password change.
Requests for known and unknown addresses get the same confirmation page.
Repeated requests for the same normalized address are limited to once a minute.
The mail cooldown uses Django's configured cache; use shared cache storage
when scaling across application workers/instances.

## Selected sender: noreply@fastlap.ru (Timeweb mail)

Create the mailbox in the provider's Mail section for fastlap.ru, then set:

```dotenv
EMAIL_HOST=smtp.timeweb.ru
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
EMAIL_HOST_USER=noreply@fastlap.ru
DEFAULT_FROM_EMAIL=Fastlap <noreply@fastlap.ru>
SITE_URL=https://fastlap.ru
```

Set EMAIL_HOST_PASSWORD to the mailbox password in the hosting environment.
The mailbox and its password have NOT been created by this code change.
Use the DNS values provided by the mail setup wizard rather than replacing
existing mail records blindly.

- https://timeweb.cloud/docs/mail/mail-settings/create-mailbox
- https://timeweb.cloud/docs/mail/email-clients-configuration
