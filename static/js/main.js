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

    function toPersianDigits(value) {
        const persian = "۰۱۲۳۴۵۶۷۸۹";
        return String(value).replace(/[0-9]/g, function (digit) {
            return persian[Number(digit)];
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
       ۳. تأیید خروج از حساب

       دکمه‌های خروج در واقع لینک به صفحه تأیید هستند. اینجا کلیک را
       می‌گیریم و به‌جای رفتن به آن صفحه، پنجره تأیید را باز می‌کنیم.

       چرا این‌طور؟ اگر دکمه را فقط با جاوااسکریپت می‌ساختیم، کاربری که
       جاوااسکریپت ندارد اصلاً نمی‌توانست خارج شود. با این روش، بدون
       جاوااسکریپت هم صفحه تأیید باز می‌شود و خروج ممکن است.
       --------------------------------------------------------------------- */
    const logoutModalElement = document.getElementById("logoutModal");

    if (logoutModalElement && window.bootstrap) {
        const logoutModal = new window.bootstrap.Modal(logoutModalElement);

        document.querySelectorAll("[data-logout-trigger]").forEach(function (trigger) {
            trigger.addEventListener("click", function (event) {
                event.preventDefault();
                logoutModal.show();
            });
        });
    }

    /* ---------------------------------------------------------------------
       ۴. شمارنده ارسال مجدد کد تأیید

       دکمه «ارسال مجدد» تا پایان زمان انتظار غیرفعال است. سرور هم همین
       محدودیت را جداگانه اعمال می‌کند؛ این شمارنده فقط برای اینکه کاربر
       بداند چقدر باید صبر کند.
       --------------------------------------------------------------------- */
    document.querySelectorAll("[data-resend-button]").forEach(function (button) {
        let remaining = parseInt(button.dataset.resendSeconds, 10) || 0;
        if (remaining <= 0) return;

        const label = button.querySelector("[data-resend-label]");
        const timer = button.querySelector("[data-resend-timer]");

        const tick = setInterval(function () {
            remaining -= 1;

            if (remaining <= 0) {
                clearInterval(tick);
                button.disabled = false;
                if (label) label.textContent = "ارسال مجدد کد";
                return;
            }

            // ارقام شمارنده هم مثل بقیه سایت فارسی نمایش داده می‌شوند
            if (timer) timer.textContent = toPersianDigits(remaining);
        }, 1000);
    });

    /* ---------------------------------------------------------------------
       ۵. اسلایدر تصویری صفحه اصلی
       - به‌صورت خودکار (با فاصله تنظیم‌شده در پنل مدیریت) به اسلاید بعدی می‌رود
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

        /**
         * بارگذاری تصویر یک اسلاید در صورت نیاز.
         * اسلایدهای سوم به بعد آدرس تصویرشان در data-src نگه داشته شده تا
         * هنگام باز شدن صفحه دانلود نشوند. اینجا درست قبل از نمایش، آدرس
         * واقعی را ست می‌کنیم.
         */
        function loadSlideImage(slide) {
            if (!slide) return;

            slide.querySelectorAll("source[data-srcset]").forEach(function (source) {
                source.srcset = source.dataset.srcset;
                delete source.dataset.srcset;
            });

            slide.querySelectorAll("img[data-src]").forEach(function (img) {
                img.src = img.dataset.src;
                delete img.dataset.src;
            });
        }

        function show(index) {
            current = (index + slides.length) % slides.length;

            // اسلاید فعلی و اسلاید بعدی را آماده نگه می‌داریم تا جابه‌جایی
            // بدون مکث و بدون تصویر خالی انجام شود.
            loadSlideImage(slides[current]);
            loadSlideImage(slides[(current + 1) % slides.length]);

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


/* =========================================================================
   کپی کردن نشانی دوره
   -------------------------------------------------------------------------
   چرا اینقدر مفصل برای یک دکمه کپی؟
   متد مدرن navigator.clipboard فقط روی اتصال امن (https یا localhost) کار
   می‌کند. اگر سایت روی http باز شود، این متد اصلاً وجود ندارد و دکمه بی‌صدا
   بی‌اثر می‌شود. پس یک روش قدیمی‌تر هم به‌عنوان پشتیبان نگه می‌داریم.
   ========================================================================= */
(function () {
    "use strict";

    function legacyCopy(text) {
        const field = document.createElement("textarea");
        field.value = text;
        field.setAttribute("readonly", "");
        field.style.position = "fixed";
        field.style.opacity = "0";
        document.body.appendChild(field);
        field.select();

        let copied = false;
        try {
            copied = document.execCommand("copy");
        } catch (error) {
            copied = false;
        }
        document.body.removeChild(field);
        return copied;
    }

    document.querySelectorAll("[data-copy-link]").forEach(function (button) {
        const container = button.closest("[data-share-url]");
        if (!container) return;

        const url = container.getAttribute("data-share-url");
        const feedback = container.querySelector("[data-copy-feedback]");

        function announce(message) {
            if (!feedback) return;
            feedback.textContent = message;
            feedback.hidden = false;
            window.setTimeout(function () { feedback.hidden = true; }, 2500);
        }

        button.addEventListener("click", function () {
            if (navigator.clipboard && window.isSecureContext) {
                navigator.clipboard.writeText(url).then(
                    function () { announce("لینک کپی شد"); },
                    function () { announce("کپی نشد؛ نشانی را از نوار آدرس بردارید."); }
                );
                return;
            }

            announce(legacyCopy(url) ? "لینک کپی شد" : "کپی نشد؛ نشانی را از نوار آدرس بردارید.");
        });
    });
})();


/* =========================================================================
   ادامه دادن ویدیو از همان جایی که رها شده بود
   -------------------------------------------------------------------------
   این قابلیت کاملاً اختیاری است. اگر جاوااسکریپت خاموش باشد یا این کد
   خطا بدهد، ویدیو فقط از ابتدا پخش می‌شود و هیچ بخش دیگری از صفحه —
   از جمله دکمه «تکمیل کردم» که یک فرم معمولی است — خراب نمی‌شود.

   موقعیت هر ۱۵ ثانیه ذخیره می‌شود، نه هر ثانیه؛ وگرنه برای یک ویدیوی
   نیم‌ساعته هزار و هشتصد درخواست به سرور می‌رفت.
   ========================================================================= */
(function () {
    "use strict";

    const SAVE_EVERY_SECONDS = 15;

    function csrfToken() {
        const field = document.querySelector("[name=csrfmiddlewaretoken]");
        return field ? field.value : "";
    }

    document.querySelectorAll("[data-lesson-player]").forEach(function (box) {
        const video = box.querySelector("video");
        if (!video) return;

        const url = box.getAttribute("data-position-url");
        const resumeAt = parseInt(box.getAttribute("data-resume-at"), 10) || 0;
        let lastSaved = resumeAt;

        // پرش به موقعیت قبلی، فقط وقتی مرورگر مدت ویدیو را می‌داند و
        // کاربر واقعاً وسط ویدیو بوده (نه ثانیه‌های اول یا انتهای آن).
        video.addEventListener("loadedmetadata", function () {
            if (resumeAt > 5 && resumeAt < video.duration - 5) {
                video.currentTime = resumeAt;
            }
        });

        function save(seconds) {
            if (!url) return;

            const body = new FormData();
            body.append("csrfmiddlewaretoken", csrfToken());
            body.append("seconds", String(Math.floor(seconds)));

            // keepalive یعنی اگر کاربر همان لحظه صفحه را ببندد، مرورگر
            // درخواست را نیمه‌کاره رها نمی‌کند.
            fetch(url, { method: "POST", body: body, keepalive: true }).catch(function () {
                // ذخیره نشدن موقعیت مشکل مهمی نیست؛ کاربر نباید خطا ببیند.
            });
        }

        video.addEventListener("timeupdate", function () {
            if (Math.abs(video.currentTime - lastSaved) < SAVE_EVERY_SECONDS) return;
            lastSaved = video.currentTime;
            save(video.currentTime);
        });

        video.addEventListener("pause", function () { save(video.currentTime); });

        // پایان ویدیو یعنی از اول شروع شود، نه اینکه در ثانیه آخر بماند.
        video.addEventListener("ended", function () { save(0); });

        window.addEventListener("pagehide", function () { save(video.currentTime); });
    });
})();
