#!/usr/bin/env python
"""ابزار خط فرمان Django برای اجرای دستورات مدیریتی پروژه."""

import os
import sys


def main() -> None:
    # به‌صورت پیش‌فرض از تنظیمات محیط توسعه استفاده می‌کنیم.
    # در سرور با تعریف متغیر محیطی DJANGO_SETTINGS_MODULE=config.settings.prod
    # این مقدار بازنویسی می‌شود.
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Django پیدا نشد. آیا Virtual Environment را فعال کرده‌اید و "
            "دستور pip install -r requirements.txt را اجرا کرده‌اید؟"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
