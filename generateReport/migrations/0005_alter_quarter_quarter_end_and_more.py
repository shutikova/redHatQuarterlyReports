# Generated by Django 4.1.7 on 2023-03-10 20:34

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("generateReport", "0004_alter_quarter_quarter_end_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="quarter",
            name="quarter_end",
            field=models.DateTimeField(
                default=datetime.datetime(
                    2023, 3, 10, 20, 34, 48, 364046, tzinfo=datetime.timezone.utc
                )
            ),
        ),
        migrations.AlterField(
            model_name="quarter",
            name="quarter_start",
            field=models.DateTimeField(
                default=datetime.datetime(
                    2023, 3, 10, 20, 34, 48, 364028, tzinfo=datetime.timezone.utc
                )
            ),
        ),
    ]