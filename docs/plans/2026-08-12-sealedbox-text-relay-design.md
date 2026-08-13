# Sealed-box text and relay design

## User flow

The `/crypto` private-chat command opens the existing sealed-box menu after
clearing the previous FSM state and tracked UI message. Encryption accepts text
or a file. After selecting a recipient, the prompt includes the shortened
recipient address. The result is one document message with a Home button and a
caption naming the recipient. When the Base64 ciphertext also fits Telegram's
1024-character document-caption limit, the caption includes it as monospace
text; otherwise the document remains the only ciphertext representation.

Decryption accepts either an uploaded encrypted document or Base64 pasted as a
message. Both inputs enter the existing wallet-specific decryption path. Pasted
Base64 uses the inferred text output filename because it carries no original
filename metadata.

## WebApp server relay

Browser decryption remains local by default. If native file sharing is
unsupported or fails, the page reveals an explicit “send through server”
button. Only that user action uploads the decrypted bytes. The owner-checked
endpoint stores the payload in the existing request hash with the existing
10-minute TTL, marks it relay-pending, and publishes a dedicated Redis queue
message.

The bot worker verifies token ownership and status, sends the document with a
Home button, then clears FSM state, releases delayed notifications, and deletes
the Redis request. Plaintext is never logged or written to disk. Worker failure
leaves the TTL-bound request available for queue retry; successful delivery
removes it immediately.

## Verification

Router tests cover command entry, Base64 input, recipient-aware prompts, and
single-message encryption results. WebApp tests cover owner checks, size limits,
and relay queue publication. Worker tests verify Telegram delivery and Redis
cleanup. Static WebApp tests ensure plaintext upload is only wired to the
explicit relay button.
