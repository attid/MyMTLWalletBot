/**
 * BiometricStorage - Telegram BiometricManager wrapper
 *
 * Uses Telegram's BiometricManager API to securely store keys
 * on mobile devices with biometric authentication.
 */
const BiometricStorage = {
    async _ensureInit() {
        const tg = window.Telegram?.WebApp;
        if (!tg?.BiometricManager) {
            throw new Error("BiometricManager недоступен");
        }

        return new Promise((resolve, reject) => {
            const timeout = setTimeout(() => {
                reject(new Error("Таймаут инициализации BiometricManager"));
            }, 5000);

            if (tg.BiometricManager.isInited) {
                clearTimeout(timeout);
                resolve(tg.BiometricManager);
            } else {
                tg.BiometricManager.init(() => {
                    clearTimeout(timeout);
                    resolve(tg.BiometricManager);
                });
            }
        });
    },

    async isAvailable() {
        try {
            const bm = await this._ensureInit();
            return bm.isBiometricAvailable;
        } catch (e) {
            console.error("BiometricStorage.isAvailable error:", e);
            return false;
        }
    },

    async requestAccess(reason) {
        const bm = await this._ensureInit();
        return new Promise(resolve => {
            bm.requestAccess({ reason }, granted => resolve(granted));
        });
    },

    async saveKey(secretKey) {
        const bm = await this._ensureInit();
        return new Promise(resolve => {
            bm.updateBiometricToken(secretKey, success => resolve(success));
        });
    },

    async authenticate(reason) {
        const bm = await this._ensureInit();

        if (!bm.isBiometricAvailable) {
            throw new Error("Биометрия недоступна на этом устройстве");
        }

        if (!bm.isBiometricTokenSaved) {
            throw new Error("Биометрический токен не сохранен. Переимпортируйте ключ.");
        }

        return new Promise(resolve => {
            bm.authenticate({ reason }, (success, token) => resolve(success ? token : null));
        });
    },

    isBiometricTokenSaved() {
        const tg = window.Telegram?.WebApp;
        return tg?.BiometricManager?.isBiometricTokenSaved || false;
    }
};

/**
 * CryptoStorage - Secure key storage using Web Crypto API
 *
 * Keys are encrypted with AES-GCM using a key derived from password.
 * Stored in IndexedDB for persistence across sessions.
 * Supports two modes:
 * - "biometric": key stored via Telegram BiometricManager
 * - "password": key encrypted with user-provided password
 */

const CryptoStorage = (function() {
    const DB_NAME = "mmwb_keys";
    const DB_VERSION = 2;  // Bumped for mode support
    const STORE_NAME = "keys";

    // Derive AES key from password using PBKDF2
    async function deriveKeyFromPassword(password, salt) {
        const encoder = new TextEncoder();
        const keyMaterial = await crypto.subtle.importKey(
            "raw",
            encoder.encode(password),
            "PBKDF2",
            false,
            ["deriveKey"]
        );

        return crypto.subtle.deriveKey(
            {
                name: "PBKDF2",
                salt: salt,
                iterations: 100000,
                hash: "SHA-256"
            },
            keyMaterial,
            { name: "AES-GCM", length: 256 },
            false,
            ["encrypt", "decrypt"]
        );
    }

    // Open IndexedDB
    function openDB() {
        return new Promise((resolve, reject) => {
            const request = indexedDB.open(DB_NAME, DB_VERSION);

            request.onerror = () => reject(request.error);
            request.onsuccess = () => resolve(request.result);

            request.onupgradeneeded = (event) => {
                const db = event.target.result;
                if (!db.objectStoreNames.contains(STORE_NAME)) {
                    db.createObjectStore(STORE_NAME, { keyPath: "address" });
                }
                // Note: existing records without 'mode' field will be treated as legacy
                // and ignored - user must re-import keys
            };
        });
    }

    // Encrypt data with password-derived key
    async function encryptWithPassword(data, password) {
        const encoder = new TextEncoder();
        const salt = crypto.getRandomValues(new Uint8Array(16));
        const iv = crypto.getRandomValues(new Uint8Array(12));
        const key = await deriveKeyFromPassword(password, salt);

        const encrypted = await crypto.subtle.encrypt(
            { name: "AES-GCM", iv: iv },
            key,
            encoder.encode(data)
        );

        // Combine salt + IV + encrypted data
        const combined = new Uint8Array(salt.length + iv.length + encrypted.byteLength);
        combined.set(salt);
        combined.set(iv, salt.length);
        combined.set(new Uint8Array(encrypted), salt.length + iv.length);

        return btoa(String.fromCharCode(...combined));
    }

    // Decrypt data with password-derived key
    async function decryptWithPassword(encryptedBase64, password) {
        const combined = Uint8Array.from(atob(encryptedBase64), c => c.charCodeAt(0));

        const salt = combined.slice(0, 16);
        const iv = combined.slice(16, 28);
        const encrypted = combined.slice(28);

        const key = await deriveKeyFromPassword(password, salt);

        const decrypted = await crypto.subtle.decrypt(
            { name: "AES-GCM", iv: iv },
            key,
            encrypted
        );

        return new TextDecoder().decode(decrypted);
    }

    return {
        /**
         * Save key with biometric mode (key stored in BiometricManager)
         * @param {string} address - Wallet public address (GXXX...)
         * @param {string} secretKey - Secret key (SXXX...)
         */
        async saveKeyBiometric(address, secretKey) {
            // Save key in Telegram's BiometricManager
            const success = await BiometricStorage.saveKey(secretKey);
            if (!success) {
                throw new Error("Failed to save key in BiometricManager");
            }

            // Save metadata in IndexedDB
            const db = await openDB();
            return new Promise((resolve, reject) => {
                const tx = db.transaction(STORE_NAME, "readwrite");
                const store = tx.objectStore(STORE_NAME);

                const request = store.put({
                    address: address,
                    mode: "biometric",
                    createdAt: Date.now()
                });

                request.onsuccess = () => resolve();
                request.onerror = () => reject(request.error);
            });
        },

        /**
         * Save key with password mode (key encrypted with password)
         * @param {string} address - Wallet public address (GXXX...)
         * @param {string} secretKey - Secret key (SXXX...)
         * @param {string} password - User password for encryption
         */
        async saveKeyPassword(address, secretKey, password) {
            const db = await openDB();
            const encryptedKey = await encryptWithPassword(secretKey, password);

            return new Promise((resolve, reject) => {
                const tx = db.transaction(STORE_NAME, "readwrite");
                const store = tx.objectStore(STORE_NAME);

                const request = store.put({
                    address: address,
                    mode: "password",
                    encryptedKey: encryptedKey,
                    createdAt: Date.now()
                });

                request.onsuccess = () => resolve();
                request.onerror = () => reject(request.error);
            });
        },

        /**
         * Get key info (mode, address) without decrypting
         * @param {string} address - Wallet public address
         * @returns {object|null} Key info or null if not found
         */
        async getKeyInfo(address) {
            const db = await openDB();

            return new Promise((resolve, reject) => {
                const tx = db.transaction(STORE_NAME, "readonly");
                const store = tx.objectStore(STORE_NAME);
                const request = store.get(address);

                request.onsuccess = () => {
                    const result = request.result;
                    if (!result || !result.mode) {
                        // No key or legacy key without mode - treat as not found
                        resolve(null);
                        return;
                    }
                    resolve({
                        address: result.address,
                        mode: result.mode,
                        encryptedKey: result.encryptedKey,
                        createdAt: result.createdAt
                    });
                };

                request.onerror = () => reject(request.error);
            });
        },

        /**
         * Get decrypted secret key using biometric authentication
         * @param {string} address - Wallet public address
         * @param {string} reason - Reason to show in biometric prompt
         * @returns {string|null} Secret key or null if failed
         */
        async getKeyBiometric(address, reason = "Подтверждение операции") {
            const keyInfo = await this.getKeyInfo(address);
            if (!keyInfo || keyInfo.mode !== "biometric") {
                return null;
            }

            // Let errors propagate to caller for proper handling
            return await BiometricStorage.authenticate(reason);
        },

        /**
         * Get decrypted secret key using password
         * @param {string} address - Wallet public address
         * @param {string} password - User password
         * @returns {string|null} Secret key or null if wrong password
         */
        async getKeyPassword(address, password) {
            const keyInfo = await this.getKeyInfo(address);
            if (!keyInfo || keyInfo.mode !== "password") {
                return null;
            }

            try {
                return await decryptWithPassword(keyInfo.encryptedKey, password);
            } catch (e) {
                console.error("Decryption failed:", e);
                return null;
            }
        },

        /**
         * Check if key exists for address (with valid mode)
         * @param {string} address - Wallet public address
         * @returns {boolean}
         */
        async hasKey(address) {
            const keyInfo = await this.getKeyInfo(address);
            return keyInfo !== null;
        },

        /**
         * Delete key for address
         * @param {string} address - Wallet public address
         */
        async deleteKey(address) {
            const db = await openDB();

            return new Promise((resolve, reject) => {
                const tx = db.transaction(STORE_NAME, "readwrite");
                const store = tx.objectStore(STORE_NAME);
                const request = store.delete(address);

                request.onsuccess = () => resolve();
                request.onerror = () => reject(request.error);
            });
        },

        /**
         * List all stored addresses
         * @returns {string[]} Array of addresses
         */
        async listAddresses() {
            const db = await openDB();

            return new Promise((resolve, reject) => {
                const tx = db.transaction(STORE_NAME, "readonly");
                const store = tx.objectStore(STORE_NAME);
                const request = store.getAllKeys();

                request.onsuccess = () => resolve(request.result);
                request.onerror = () => reject(request.error);
            });
        },

        // --- Wallet → Signer Mapping (localStorage) ---

        /**
         * Save wallet → signer mapping
         * @param {string} walletAddress - Wallet address (the one TX is for)
         * @param {string} signerAddress - Signer's public key address
         */
        setWalletSigner(walletAddress, signerAddress) {
            const signers = JSON.parse(localStorage.getItem('mmwb_wallet_signers') || '{}');
            signers[walletAddress] = signerAddress;
            localStorage.setItem('mmwb_wallet_signers', JSON.stringify(signers));
        },

        /**
         * Get signer address for a wallet
         * @param {string} walletAddress - Wallet address
         * @returns {string|null} Signer address or null if not mapped
         */
        getWalletSigner(walletAddress) {
            const signers = JSON.parse(localStorage.getItem('mmwb_wallet_signers') || '{}');
            return signers[walletAddress] || null;
        },

        /**
         * Remove wallet → signer mapping
         * @param {string} walletAddress - Wallet address to remove
         */
        removeWalletSigner(walletAddress) {
            const signers = JSON.parse(localStorage.getItem('mmwb_wallet_signers') || '{}');
            delete signers[walletAddress];
            localStorage.setItem('mmwb_wallet_signers', JSON.stringify(signers));
        },

        /**
         * Get all wallets mapped to a signer
         * @param {string} signerAddress - Signer's public key address
         * @returns {string[]} Array of wallet addresses
         */
        getWalletsForSigner(signerAddress) {
            const signers = JSON.parse(localStorage.getItem('mmwb_wallet_signers') || '{}');
            return Object.entries(signers)
                .filter(([_, signer]) => signer === signerAddress)
                .map(([wallet, _]) => wallet);
        },

        /**
         * Remove all wallet mappings for a signer (call when deleting key)
         * @param {string} signerAddress - Signer's public key address
         */
        removeSignerMappings(signerAddress) {
            const signers = JSON.parse(localStorage.getItem('mmwb_wallet_signers') || '{}');
            const updated = {};
            for (const [wallet, signer] of Object.entries(signers)) {
                if (signer !== signerAddress) {
                    updated[wallet] = signer;
                }
            }
            localStorage.setItem('mmwb_wallet_signers', JSON.stringify(updated));
        }
    };
})();
