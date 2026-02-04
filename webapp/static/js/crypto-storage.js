/**
 * CryptoStorage - Secure key storage using Web Crypto API
 *
 * Keys are encrypted with AES-GCM using a key derived from user's Telegram ID.
 * Stored in IndexedDB for persistence across sessions.
 */

const CryptoStorage = (function() {
    const DB_NAME = "mmwb_keys";
    const DB_VERSION = 1;
    const STORE_NAME = "keys";

    // Get encryption key from Telegram user data
    async function getEncryptionKey() {
        const tg = window.Telegram?.WebApp;
        const userId = tg?.initDataUnsafe?.user?.id || "default";

        // Derive key from user ID using PBKDF2
        const encoder = new TextEncoder();
        const keyMaterial = await crypto.subtle.importKey(
            "raw",
            encoder.encode(String(userId)),
            "PBKDF2",
            false,
            ["deriveKey"]
        );

        return crypto.subtle.deriveKey(
            {
                name: "PBKDF2",
                salt: encoder.encode("mmwb_salt_v1"),
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
            };
        });
    }

    // Encrypt data
    async function encrypt(data) {
        const key = await getEncryptionKey();
        const encoder = new TextEncoder();
        const iv = crypto.getRandomValues(new Uint8Array(12));

        const encrypted = await crypto.subtle.encrypt(
            { name: "AES-GCM", iv: iv },
            key,
            encoder.encode(data)
        );

        // Combine IV + encrypted data
        const combined = new Uint8Array(iv.length + encrypted.byteLength);
        combined.set(iv);
        combined.set(new Uint8Array(encrypted), iv.length);

        return btoa(String.fromCharCode(...combined));
    }

    // Decrypt data
    async function decrypt(encryptedBase64) {
        const key = await getEncryptionKey();
        const combined = Uint8Array.from(atob(encryptedBase64), c => c.charCodeAt(0));

        const iv = combined.slice(0, 12);
        const encrypted = combined.slice(12);

        const decrypted = await crypto.subtle.decrypt(
            { name: "AES-GCM", iv: iv },
            key,
            encrypted
        );

        return new TextDecoder().decode(decrypted);
    }

    return {
        /**
         * Save encrypted secret key
         * @param {string} address - Wallet public address (GXXX...)
         * @param {string} secretKey - Secret key (SXXX...)
         */
        async saveKey(address, secretKey) {
            const db = await openDB();
            const encryptedKey = await encrypt(secretKey);

            return new Promise((resolve, reject) => {
                const tx = db.transaction(STORE_NAME, "readwrite");
                const store = tx.objectStore(STORE_NAME);

                const request = store.put({
                    address: address,
                    encryptedKey: encryptedKey,
                    createdAt: Date.now()
                });

                request.onsuccess = () => resolve();
                request.onerror = () => reject(request.error);
            });
        },

        /**
         * Get decrypted secret key
         * @param {string} address - Wallet public address
         * @returns {string|null} Secret key or null if not found
         */
        async getKey(address) {
            const db = await openDB();

            return new Promise((resolve, reject) => {
                const tx = db.transaction(STORE_NAME, "readonly");
                const store = tx.objectStore(STORE_NAME);
                const request = store.get(address);

                request.onsuccess = async () => {
                    if (!request.result) {
                        resolve(null);
                        return;
                    }

                    try {
                        const secretKey = await decrypt(request.result.encryptedKey);
                        resolve(secretKey);
                    } catch (e) {
                        console.error("Decryption failed:", e);
                        resolve(null);
                    }
                };

                request.onerror = () => reject(request.error);
            });
        },

        /**
         * Check if key exists for address
         * @param {string} address - Wallet public address
         * @returns {boolean}
         */
        async hasKey(address) {
            const db = await openDB();

            return new Promise((resolve, reject) => {
                const tx = db.transaction(STORE_NAME, "readonly");
                const store = tx.objectStore(STORE_NAME);
                const request = store.get(address);

                request.onsuccess = () => resolve(!!request.result);
                request.onerror = () => reject(request.error);
            });
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
