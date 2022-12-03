# Generated by Django 4.1.3 on 2022-12-03 18:13

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0023_rename_channel_twitchintegration_twitch_login_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='twitchintegration',
            name='followers_only',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='twitchintegration',
            name='queue_cooldown_follower',
            field=models.FloatField(default=60),
        ),
    ]
