# Generated by Django 4.0.5 on 2022-06-04 19:25

import datetime
from django.db import migrations, models
from django.utils.timezone import utc


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0006_alter_invitation_username'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='spotifyauthorization',
            name='time',
        ),
        migrations.AddField(
            model_name='spotifyauthorization',
            name='time_refreshed',
            field=models.DateTimeField(default=datetime.datetime(2022, 6, 4, 19, 25, 19, 370809, tzinfo=utc)),
            preserve_default=False,
        ),
    ]
