# Stellar Sealed-Box File Encryption Design

## Goal and scope

Add interoperable Stellar sealed-box encryption to MTL Tools. A user can
encrypt text or a Telegram document for a Stellar `G...` address and can
decrypt a document addressed to the currently active wallet. The encrypted
payload remains compatible with `https://eurmtl.me/sealedbox` and
`localdoc/stellar_sealedbox.py`.

The first release supports Stellar Ed25519 public addresses only. It does not
support TON, muxed accounts, federation addresses, usernames, sender
authentication, or a custom file container.

## User flow

MTL Tools gains a localized **File encryption** entry. Its menu contains
Encrypt, Decrypt, Back, and Home actions.

Encryption asks the user to enter a recipient `G...` address or choose one
from the existing address book. The next screen accepts ordinary text or a
Telegram document of at most 10 MiB. Other Telegram media must be resent as a
document. Text is treated as UTF-8 and named `message.txt`; documents retain a
sanitized basename. The bot returns raw sealed-box bytes with `.ssb` appended
to the filename and the caption `Encrypted for GC5Q...HYPG` (localized).

Decryption always uses the currently active wallet. There is no wallet picker
and no automatic key search. If another wallet is needed, the user changes the
active wallet using the existing wallet controls and retries. A successful
decrypt strips the final `.ssb` suffix. If the original filename is unknown,
valid UTF-8 is returned as `sealedbox-output.txt`, otherwise as
`sealedbox-output.bin`.

Wrong-key and damaged-file failures share a simple message because sealed-box
payloads do not identify their recipient. The flow remains open so the user
can send another file, go Back, or go Home.

## Cryptography and compatibility

The bot converts Stellar Ed25519 public and private keys to Curve25519 and
uses libsodium sealed boxes. Encryption returns raw bytes. Decryption tries
the supplied bytes as raw ciphertext first and, only if that fails, decodes
strict base64 and tries again. Ciphertext overhead is 48 bytes.

No metadata, filename, sender identity, magic bytes, or version header is
placed inside the ciphertext. Filename recovery therefore depends only on the
outer Telegram filename. This is required for byte-level compatibility with
the existing website and script.

The implementation exposes sealed-box operations through a focused service;
it does not extend the existing wallet-at-rest `EncryptionService`, whose
contract and threat model are unrelated.

## Key handling

Server-held no-PIN, PIN, and password wallets decrypt in the bot using the
existing active-wallet secret retrieval and authentication paths. Plaintext
and secret keys remain in memory and are never written to Redis, disk, or
logs.

For a WebApp/read-only wallet, the bot stores only ciphertext and safe output
metadata under a random Redis token with a 10-minute TTL. The WebApp validates
Telegram `initData`, verifies token ownership, downloads ciphertext, unlocks
the key from the existing browser storage using biometrics or password, and
decrypts locally. The plaintext is downloaded directly by the browser and is
never returned to the backend. Missing local keys lead to the existing import
flow. Successful completion sends only a status event to the bot, which then
cleans temporary data, completes FSM state, and releases the notification
hold.

A token may be reopened until completion or expiry so an accidental WebApp
close does not destroy the operation. A new WebApp decrypt request replaces
the user's previous request. Home deletes the pending request. Expired requests
ask the user to return to the bot and resend the file.

## Resource controls and data hygiene

Plaintext is limited to 10 MiB and ciphertext to 10 MiB plus the 48-byte
sealed-box overhead. Filenames are reduced to a basename, stripped of path and
control characters, bounded in length, and given deterministic fallbacks.

An in-process rolling limiter stores operation timestamps by Telegram user:
at most 10 encryption/decryption attempts in 60 minutes. An attempt is counted
after type and size validation and immediately before cryptographic work;
failed decrypts count. Counters reset on process restart. A process-wide
`asyncio.Semaphore(4)` bounds concurrent cryptographic operations.

Logs contain only `user_id`, operation, byte size, and result. They never
contain addresses, filenames, secret keys, ciphertext, or plaintext.

## Navigation and notifications

Every screen has distinct Back and Home actions. Back returns to the previous
screen and retains safe selections such as the encryption recipient. Home
cleans FSM state and any temporary WebApp ciphertext, clears the tracked UI
message, and releases the delayed-notification hold. Successful Telegram or
WebApp completion performs the same terminal cleanup.

The flow uses the shared Telegram screen sender so `last_message_id` remains
correct. Starting the flow clears previous FSM state and the last tracked
message before rendering its first screen.

## Verification

Unit tests cover both interoperability directions with fixed Stellar keys,
raw and strict-base64 inputs, malformed data, wrong keys, the 48-byte
overhead, filename handling, size checks, and resource limits.

Router tests use the shared `mock_telegram` fixtures and cover all navigation,
recipient, input, active-wallet, authentication, error, completion, and
notification-hold paths. WebApp tests cover owner authentication, expiry,
retry, local key lookup, local-only plaintext, download naming, completion,
and cleanup. An end-to-end deterministic test covers bot handoff to WebApp and
terminal completion. Existing signing and notification suites run as
regression coverage.
