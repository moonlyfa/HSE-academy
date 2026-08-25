/* =========================================================================
   HSE Tech — جاوااسکریپت سبک سایت
   -------------------------------------------------------------------------
   فقط چیزهایی که واقعاً به جاوااسکریپت نیاز دارند اینجا نوشته می‌شود.
   بقیه رفتارها (منوی موبایل، آکاردئون) با خود بوت‌استرپ انجام می‌شود.
   ========================================================================= */

(function () {
    "use strict";

    /* ---------------------------------------------------------------------
       ۱. تبدیل اعداد فارسی و عربی به انگلیسی
       کاربر ممکن است شماره موبایل یا کد گواهی را با کیبورد فارسی تایپ کند؛
       بدون این تبدیل، سرور مقدار را نامعتبر می‌بیند.
       --------------------------------------------------------------------- */
    function toEnglishDigits(value) {
        const persian = "۰۱۲۳۴۵۶۷۸۹";
        const arabic = "٠١٢٣٤٥٦٧٨٩";
        return value.replace(/[۰-۹٠-٩]/g, function (char) {
            const index = persian.indexOf(char);
            return index > -1 ? index : arabic.indexOf(char);
        });
    }

    document.querySelectorAll('[data-digits="en"]').forEach(function (input) {
        input.addEventListener("input", function () {
            const converted = toEnglishDigits(input.value);
            if (converted !== input.value) {
                input.value = converted;
            }
        });
    });

    /* ---------------------------------------------------------------------
       ۲. نوار جست‌وجوی هدر
       --------------------------------------------------------------------- */
    const searchBar = document.getElementById("site-search");
    const searchToggles = document.querySelectorAll("[data-search-toggle]");
    const searchClose = document.querySelector("[data-search-close]");

    function openSearch() {
        if (!searchBar) return;
        searchBar.hidden = false;
        searchToggles.forEach(function (btn) {
            btn.setAttribute("aria-expanded", "true");
        });
        const input = document.getElementById("site-search-input");
        if (input) input.focus();
    }

    function closeSearch() {
        if (!searchBar) return;
        searchBar.hidden = true;
        searchToggles.forEach(function (btn) {
            btn.setAttribute("aria-expanded", "false");
        });
    }

    searchToggles.forEach(function (btn) {
        btn.addEventListener("click", function () {
            if (searchBar && searchBar.hidden) {
                openSearch();
            } else {
                closeSearch();
            }
        });
    });

    if (searchClose) {
        searchClose.addEventListener("click", closeSearch);
    }

    // بستن نوار جست‌وجو با کلید Escape
    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && searchBar && !searchBar.hidden) {
            closeSearch();
        }
    });

    /* ---------------------------------------------------------------------
       ۳. اسلایدر تصویری صفحه اصلی
       - هر ۵ ثانیه خودکار به اسلاید بعدی می‌رود
       - کاربر با دکمه‌های کناری یا نقطه‌های پایین هم می‌تواند جابه‌جا شود
       - با بردن ماوس روی اسلایدر، چرخش موقتاً متوقف می‌شود
       --------------------------------------------------------------------- */
    document.querySelectorAll("[data-slider]").forEach(function (slider) {
        const slides = Array.from(slider.querySelectorAll("[data-slider-slide]"));
        if (slides.length < 2) return; // با یک اسلاید نیازی به چرخش نیست

        const dots = Array.from(slider.querySelectorAll("[data-slider-dot]"));
        const interval = parseInt(slider.dataset.sliderInterval, 10) || 5000;
        let current = 0;
        let timer = null;

        function show(index) {
            current = (index + slides.length) % slides.length;

            slides.forEach(function (slide, i) {
                const isActive = i === current;
                slide.classList.toggle("is-active", isActive);
                // اسلایدهای پنهان نباید توسط صفحه‌خوان خوانده شوند
                slide.setAttribute("aria-hidden", isActive ? "false" : "true");
            });

            dots.forEach(function (dot, i) {
                const isActive = i === current;
                dot.classList.toggle("is-active", isActive);
                dot.setAttribute("aria-selected", isActive ? "true" : "false");
            });
        }

        function next() { show(current + 1); }
        function prev() { show(current - 1); }

        function start() {
            stop();
            timer = setInterval(next, interval);
        }

        function stop() {
            if (timer) {
                clearInterval(timer);
                timer = null;
            }
        }

        // بعد از هر حرکت دستی، تایمر از نو شمرده می‌شود تا اسلاید
        // بلافاصله بعد از کلیک کاربر عوض نشود.
        function goManually(action) {
            action();
            start();
        }

        const nextBtn = slider.querySelector("[data-slider-next]");
        const prevBtn = slider.querySelector("[data-slider-prev]");

        if (nextBtn) nextBtn.addEventListener("click", function () { goManually(next); });
        if (prevBtn) prevBtn.addEventListener("click", function () { goManually(prev); });

        dots.forEach(function (dot) {
            dot.addEventListener("click", function () {
                goManually(function () { show(parseInt(dot.dataset.index, 10)); });
            });
        });

        slider.addEventListener("mouseenter", stop);
        slider.addEventListener("mouseleave", start);

        // وقتی کاربر تب را عوض می‌کند، چرخش را متوقف می‌کنیم تا منابع هدر نرود.
        document.addEventListener("visibilitychange", function () {
            if (document.hidden) { stop(); } else { start(); }
        });

        // پشتیبانی از کشیدن با انگشت روی موبایل
        let touchStartX = null;
        slider.addEventListener("touchstart", function (event) {
            touchStartX = event.changedTouches[0].screenX;
            stop();
        }, { passive: true });

        slider.addEventListener("touchend", function (event) {
            if (touchStartX === null) return;
            const delta = event.changedTouches[0].screenX - touchStartX;
            if (Math.abs(delta) > 50) {
                // در چیدمان راست‌به‌چپ، کشیدن به راست یعنی اسلاید بعدی
                goManually(delta > 0 ? next : prev);
            } else {
                start();
            }
            touchStartX = null;
        }, { passive: true });

        show(0);
        start();
    });
})();
