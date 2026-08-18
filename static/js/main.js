/* =========================================================================
   آکادمی HSE — جاوااسکریپت سبک سایت
   -------------------------------------------------------------------------
   فقط چیزهایی که واقعاً به جاوااسکریپت نیاز دارند اینجا نوشته می‌شود.
   بقیه رفتارها (منوی موبایل، آکاردئون) با خود بوت‌استرپ انجام می‌شود.
   ========================================================================= */

(function () {
    "use strict";

    /**
     * تبدیل اعداد فارسی و عربی به انگلیسی.
     * کاربر ممکن است کد گواهی یا شماره موبایل را با کیبورد فارسی تایپ کند؛
     * بدون این تبدیل، سرور مقدار را نامعتبر می‌بیند.
     */
    function toEnglishDigits(value) {
        const persian = "۰۱۲۳۴۵۶۷۸۹";
        const arabic = "٠١٢٣٤٥٦٧٨٩";
        return value.replace(/[۰-۹٠-٩]/g, function (char) {
            const index = persian.indexOf(char);
            return index > -1 ? index : arabic.indexOf(char);
        });
    }

    // روی هر ورودی با data-digits="en" اعمال می‌شود.
    document.querySelectorAll('[data-digits="en"]').forEach(function (input) {
        input.addEventListener("input", function () {
            const converted = toEnglishDigits(input.value);
            if (converted !== input.value) {
                input.value = converted;
            }
        });
    });
})();
