"""
نام سایت از «HSE Tech» به «سپر آکادمی» تغییر کرد.

علاوه بر مقدار پیش‌فرض، سایت‌هایی که هنوز نام قدیمی را دارند هم به‌روز
می‌شوند. اگر مدیر نام دیگری از پنل گذاشته باشد، دست نمی‌خورد.
"""

from django.db import migrations, models

OLD_NAMES = ("HSE Tech", "آکادمی HSE", "")
NEW_NAME = "سپر آکادمی"


def rename_site(apps, schema_editor):
    SiteSetting = apps.get_model("core", "SiteSetting")
    SiteSetting.objects.filter(site_name__in=OLD_NAMES).update(site_name=NEW_NAME)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0005_sitesetting_card_transfer"),
    ]

    operations = [
        migrations.AlterField(
            model_name="sitesetting",
            name="site_name",
            field=models.CharField(
                default="سپر آکادمی", max_length=100, verbose_name="نام سایت"
            ),
        ),
        migrations.RunPython(rename_site, migrations.RunPython.noop),
    ]
