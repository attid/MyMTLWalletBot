(function () {
    "use strict";

    const token = window.SEALEDBOX_TOKEN;
    const tg = Telegram.WebApp;
    const headers = {"X-Telegram-Init-Data": tg.initData || ""};
    let metadata = null;
    let ciphertext = null;
    let downloadUrl = null;
    let decryptedFile = null;

    tg.ready();
    tg.expand();

    function show(id) {
        document.getElementById(id).classList.remove("hidden");
    }

    function hide(id) {
        document.getElementById(id).classList.add("hidden");
    }

    function showError(message) {
        ["loading-card", "decrypt-card", "password-card", "missing-key-card", "success-card"].forEach(hide);
        document.getElementById("error-message").textContent = message;
        show("error-card");
    }

    async function fetchJson(url, options = {}) {
        const response = await fetch(url, {...options, headers});
        if (!response.ok) {
            let detail = t("sealedbox.expired");
            try {
                detail = (await response.json()).detail || detail;
            } catch (_) {
                // Keep the localized fallback.
            }
            throw new Error(detail);
        }
        return response.json();
    }

    async function initialize() {
        if (!token) {
            showError(t("sealedbox.expired"));
            return;
        }
        try {
            metadata = await fetchJson(`/api/sealedbox/${token}`);
            const response = await fetch(`/api/sealedbox/${token}/ciphertext`, {headers});
            if (!response.ok) throw new Error(t("sealedbox.expired"));
            ciphertext = new Uint8Array(await response.arrayBuffer());
            document.getElementById("wallet-address").textContent = formatAddress(metadata.wallet_address);
            const keyInfo = await CryptoStorage.getKeyInfo(metadata.wallet_address);
            hide("loading-card");
            if (!keyInfo) {
                show("missing-key-card");
                return;
            }
            document.getElementById("decrypt-button").dataset.mode = keyInfo.mode;
            show("decrypt-card");
        } catch (error) {
            showError(error.message);
        }
    }

    async function unlockAndDecrypt(mode, password = "") {
        let secretKey = null;
        if (mode === "biometric") {
            secretKey = await CryptoStorage.getKeyBiometric(
                metadata.wallet_address,
                t("sealedbox.biometric_reason")
            );
        } else if (mode === "password") {
            secretKey = await CryptoStorage.getKeyPassword(metadata.wallet_address, password);
        }
        if (!secretKey) throw new Error(t("sign.password_wrong"));
        await sodium.ready;
        const stellarKey = StellarSdk.Keypair.fromSecret(secretKey);
        const signKeys = sodium.crypto_sign_seed_keypair(stellarKey.rawSecretKey());
        const curvePublic = sodium.crypto_sign_ed25519_pk_to_curve25519(signKeys.publicKey);
        const curvePrivate = sodium.crypto_sign_ed25519_sk_to_curve25519(signKeys.privateKey);
        const plaintext = sodium.crypto_box_seal_open(ciphertext, curvePublic, curvePrivate);
        if (!plaintext) throw new Error(t("sealedbox.decrypt_failed"));
        prepareResult(plaintext, outputFilename(plaintext));
        await fetchJson(`/api/sealedbox/${token}/complete`, {method: "POST"});
        hide("decrypt-card");
        hide("password-card");
        show("success-card");
    }

    function outputFilename(plaintext) {
        if (metadata.output_filename) return metadata.output_filename;
        try {
            new TextDecoder("utf-8", {fatal: true}).decode(plaintext);
            return "sealedbox-output.txt";
        } catch (_) {
            return "sealedbox-output.bin";
        }
    }

    function prepareResult(plaintext, filename) {
        cleanupDownload();
        decryptedFile = new File(
            [plaintext],
            filename,
            {type: mimeTypeFor(filename)}
        );
        downloadUrl = URL.createObjectURL(decryptedFile);
        const link = document.getElementById("download-fallback");
        link.href = downloadUrl;
        link.download = filename;
        try {
            const text = new TextDecoder("utf-8", {fatal: true}).decode(plaintext);
            document.getElementById("plaintext-output").textContent = text;
            show("plaintext-card");
        } catch (_) {
            hide("plaintext-card");
        }
    }

    function mimeTypeFor(filename) {
        const extension = filename.split(".").pop().toLowerCase();
        return {
            txt: "text/plain",
            json: "application/json",
            pdf: "application/pdf",
            png: "image/png",
            jpg: "image/jpeg",
            jpeg: "image/jpeg",
            webp: "image/webp",
            zip: "application/zip",
        }[extension] || "application/octet-stream";
    }

    function cleanupDownload() {
        if (downloadUrl) URL.revokeObjectURL(downloadUrl);
        downloadUrl = null;
        decryptedFile = null;
    }

    async function saveDecryptedFile() {
        if (!decryptedFile) return;
        const error = document.getElementById("download-error");
        error.textContent = "";
        try {
            if (
                navigator.share &&
                navigator.canShare &&
                navigator.canShare({files: [decryptedFile]})
            ) {
                await navigator.share({files: [decryptedFile], title: decryptedFile.name});
                return;
            }
            document.getElementById("download-fallback").click();
            error.textContent = t("sealedbox.share_unsupported");
        } catch (shareError) {
            if (shareError.name !== "AbortError") {
                error.textContent = t("sealedbox.share_failed");
            }
        }
    }

    function formatAddress(address) {
        return address.length > 12 ? `${address.slice(0, 6)}…${address.slice(-6)}` : address;
    }

    document.getElementById("decrypt-button").addEventListener("click", async (event) => {
        const mode = event.currentTarget.dataset.mode;
        if (mode === "password") {
            hide("decrypt-card");
            show("password-card");
            document.getElementById("password-input").focus();
            return;
        }
        try {
            await unlockAndDecrypt(mode);
        } catch (error) {
            showError(error.message);
        }
    });

    document.getElementById("password-button").addEventListener("click", async () => {
        try {
            await unlockAndDecrypt("password", document.getElementById("password-input").value);
        } catch (error) {
            showError(error.message);
        }
    });

    document.getElementById("import-button").addEventListener("click", () => {
        const lang = new URLSearchParams(window.location.search).get("lang") || "en";
        window.location.href = `/import?address=${encodeURIComponent(metadata.wallet_address)}&lang=${encodeURIComponent(lang)}`;
    });

    document.getElementById("save-file-button").addEventListener("click", saveDecryptedFile);
    window.addEventListener("pagehide", cleanupDownload);
    initialize();
})();
