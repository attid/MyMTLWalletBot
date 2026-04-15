// Simple i18n for the webapp.
// Language is read from the URL query param `?lang=ru|en` that the bot
// appends when building WebAppInfo URLs in bot/keyboards/webapp.py.
// Telegram.WebApp.initDataUnsafe.user.language_code is intentionally NOT
// used — we follow the explicit language chosen by the user in the bot.

(function () {
    const I18N = {
        ru: {
            "common.close": "Закрыть",
            "common.cancel": "Отмена",
            "common.confirm": "Подтвердить",
            "common.back": "Назад",
            "common.error_title": "Ошибка",
            "common.layout_warning": "⚠️ Включена русская раскладка",
            "common.retry": "Попробовать снова",
            "common.wallet_label": "Кошелек:",

            "sign.page_title": "Подписание транзакции",
            "sign.loading": "Загрузка транзакции...",
            "sign.card_title": "Подтвердите транзакцию",
            "sign.key_saved_hint": "Ключ сохранен в этом устройстве",
            "sign.btn_sign": "Подписать",
            "sign.btn_sign_in_progress": "Подписание...",
            "sign.enter_hint": "Можно нажать Enter",
            "sign.select_key_hint": "Выберите ключ для подписания или добавьте новый",
            "sign.btn_add_new_key": "Добавить новый ключ",
            "sign.btn_show_xdr": "Показать XDR",
            "sign.no_key_hint": "Ключ не найден на этом устройстве",
            "sign.btn_add_key": "Добавить ключ",
            "sign.xdr_copy_hint": "Скопируйте XDR и подпишите вручную:",
            "sign.btn_copy_xdr": "Копировать XDR",
            "sign.xdr_copied": "XDR скопирован",
            "sign.password_title": "Введите пароль",
            "sign.password_hint": "Для доступа к ключу",
            "sign.password_placeholder": "Пароль",
            "sign.password_checking": "Проверка...",
            "sign.password_empty": "Введите пароль",
            "sign.password_wrong": "Неверный пароль",
            "sign.success_title": "Транзакция подписана",
            "sign.success_body": "Транзакция отправлена на обработку",
            "sign.btn_select": "Выбрать",
            "sign.tx_id_missing": "ID транзакции не указан",
            "sign.tx_not_found": "Транзакция не найдена",
            "sign.tx_already_signed": "Транзакция уже подписана",
            "sign.tx_already_processed": "Транзакция уже обработана",
            "sign.send_error": "Ошибка отправки",
            "sign.key_not_found": "Ключ не найден",
            "sign.biometric_reason": "Подписание транзакции",
            "sign.biometric_cancelled": "Биометрия отменена",
            "sign.biometric_error": "Ошибка биометрии",
            "sign.unknown_protection": "Неизвестный тип защиты ключа",

            "import.page_title": "Добавить ключ",
            "import.card_title": "Добавить ключ",
            "import.intro": "Введите секретный ключ (начинается с S). Ключ будет зашифрован и сохранен только на этом устройстве.",
            "import.secret_label": "Секретный ключ",
            "import.mode_label": "Способ защиты ключа:",
            "import.mode_biometric": "Биометрия",
            "import.mode_biometric_desc": "Face ID / Touch ID / Отпечаток",
            "import.mode_password": "Пароль",
            "import.mode_password_desc": "Защита паролем",
            "import.password_label": "Пароль",
            "import.password_placeholder": "Введите пароль",
            "import.password_confirm_label": "Подтверждение пароля",
            "import.password_confirm_placeholder": "Повторите пароль",
            "import.consent": "Я понимаю, что ключ будет сохранен в браузере этого устройства",
            "import.btn_save": "Сохранить ключ",
            "import.btn_saving": "Сохранение...",
            "import.success_title": "Ключ сохранен",
            "import.address_label": "Адрес:",
            "import.success_hint": "Теперь вы можете подписывать транзакции",
            "import.wallet_address_missing": "Адрес кошелька не указан",
            "import.invalid_key_format": "Неверный формат ключа",
            "import.invalid_secret_key": "Неверный секретный ключ",
            "import.select_protection": "Выберите способ защиты ключа",
            "import.password_too_short": "Пароль должен быть минимум 4 символа",
            "import.password_mismatch": "Пароли не совпадают",
            "import.biometric_reason": "Для безопасного хранения ключа",
            "import.biometric_access_denied": "Доступ к биометрии не предоставлен",
            "import.save_error": "Ошибка сохранения: {msg}",

            "settings.page_title": "Управление ключами",
            "settings.card_title": "Сохраненные ключи",
            "settings.no_keys": "Нет сохраненных ключей",
            "settings.mode_biometric": "Биометрия",
            "settings.mode_password": "Пароль",
            "settings.wallets_label": "Кошельки:",
            "settings.delete_title": "Удалить",
            "settings.delete_confirm": "Удалить ключ {address}?",
            "settings.key_deleted": "Ключ удален",
            "settings.error_prefix": "Ошибка: {msg}",
        },
        en: {
            "common.close": "Close",
            "common.cancel": "Cancel",
            "common.confirm": "Confirm",
            "common.back": "Back",
            "common.error_title": "Error",
            "common.layout_warning": "⚠️ Russian keyboard layout detected",
            "common.retry": "Try again",
            "common.wallet_label": "Wallet:",

            "sign.page_title": "Sign transaction",
            "sign.loading": "Loading transaction...",
            "sign.card_title": "Confirm transaction",
            "sign.key_saved_hint": "Key is saved on this device",
            "sign.btn_sign": "Sign",
            "sign.btn_sign_in_progress": "Signing...",
            "sign.enter_hint": "Press Enter to sign",
            "sign.select_key_hint": "Select a key to sign with or add a new one",
            "sign.btn_add_new_key": "Add new key",
            "sign.btn_show_xdr": "Show XDR",
            "sign.no_key_hint": "No key found on this device",
            "sign.btn_add_key": "Add key",
            "sign.xdr_copy_hint": "Copy the XDR and sign manually:",
            "sign.btn_copy_xdr": "Copy XDR",
            "sign.xdr_copied": "XDR copied",
            "sign.password_title": "Enter password",
            "sign.password_hint": "To unlock the key",
            "sign.password_placeholder": "Password",
            "sign.password_checking": "Checking...",
            "sign.password_empty": "Enter a password",
            "sign.password_wrong": "Wrong password",
            "sign.success_title": "Transaction signed",
            "sign.success_body": "Transaction submitted for processing",
            "sign.btn_select": "Select",
            "sign.tx_id_missing": "Transaction ID is missing",
            "sign.tx_not_found": "Transaction not found",
            "sign.tx_already_signed": "Transaction already signed",
            "sign.tx_already_processed": "Transaction already processed",
            "sign.send_error": "Submit error",
            "sign.key_not_found": "Key not found",
            "sign.biometric_reason": "Sign transaction",
            "sign.biometric_cancelled": "Biometrics cancelled",
            "sign.biometric_error": "Biometric error",
            "sign.unknown_protection": "Unknown key protection type",

            "import.page_title": "Add key",
            "import.card_title": "Add key",
            "import.intro": "Enter a secret key (starts with S). The key will be encrypted and stored only on this device.",
            "import.secret_label": "Secret key",
            "import.mode_label": "Key protection method:",
            "import.mode_biometric": "Biometrics",
            "import.mode_biometric_desc": "Face ID / Touch ID / Fingerprint",
            "import.mode_password": "Password",
            "import.mode_password_desc": "Password protection",
            "import.password_label": "Password",
            "import.password_placeholder": "Enter password",
            "import.password_confirm_label": "Confirm password",
            "import.password_confirm_placeholder": "Repeat password",
            "import.consent": "I understand the key will be stored in this device's browser",
            "import.btn_save": "Save key",
            "import.btn_saving": "Saving...",
            "import.success_title": "Key saved",
            "import.address_label": "Address:",
            "import.success_hint": "You can now sign transactions",
            "import.wallet_address_missing": "Wallet address is missing",
            "import.invalid_key_format": "Invalid key format",
            "import.invalid_secret_key": "Invalid secret key",
            "import.select_protection": "Select a key protection method",
            "import.password_too_short": "Password must be at least 4 characters",
            "import.password_mismatch": "Passwords do not match",
            "import.biometric_reason": "To securely store the key",
            "import.biometric_access_denied": "Biometric access was not granted",
            "import.save_error": "Save error: {msg}",

            "settings.page_title": "Manage keys",
            "settings.card_title": "Saved keys",
            "settings.no_keys": "No saved keys",
            "settings.mode_biometric": "Biometrics",
            "settings.mode_password": "Password",
            "settings.wallets_label": "Wallets:",
            "settings.delete_title": "Delete",
            "settings.delete_confirm": "Delete key {address}?",
            "settings.key_deleted": "Key deleted",
            "settings.error_prefix": "Error: {msg}",
        },
    };

    function getLangFromURL() {
        const raw = new URLSearchParams(window.location.search).get("lang");
        return raw === "ru" || raw === "en" ? raw : "en";
    }

    function t(key, params) {
        const lang = window.__LANG || "en";
        let template = (I18N[lang] && I18N[lang][key]) || I18N.en[key];
        if (template == null) {
            console.warn("[i18n] missing key:", key);
            return key;
        }
        if (params) {
            for (const [name, value] of Object.entries(params)) {
                template = template.split("{" + name + "}").join(String(value));
            }
        }
        return template;
    }

    function applyTranslations(root) {
        const scope = root || document;
        scope.querySelectorAll("[data-i18n]").forEach((el) => {
            el.textContent = t(el.getAttribute("data-i18n"));
        });
        scope.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
            el.setAttribute(
                "placeholder",
                t(el.getAttribute("data-i18n-placeholder"))
            );
        });
        scope.querySelectorAll("[data-i18n-title]").forEach((el) => {
            el.setAttribute("title", t(el.getAttribute("data-i18n-title")));
        });
    }

    window.__LANG = getLangFromURL();
    window.I18N = I18N;
    window.t = t;
    window.applyTranslations = applyTranslations;

    document.addEventListener("DOMContentLoaded", () => {
        document.documentElement.setAttribute("lang", window.__LANG);
        applyTranslations();
        const titleKey = document.documentElement.getAttribute("data-i18n-page-title");
        if (titleKey) {
            document.title = t(titleKey);
        }
    });
})();
