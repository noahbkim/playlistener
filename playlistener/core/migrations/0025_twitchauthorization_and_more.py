# Generated by Django 4.1.3 on 2022-12-07 05:39

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('core', '0024_twitchintegration_followers_only_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='TwitchAuthorization',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('access_token', models.CharField(max_length=250)),
                ('refresh_token', models.CharField(max_length=250)),
                ('token_type', models.CharField(max_length=50)),
                ('expires_in', models.PositiveIntegerField()),
                ('scope', models.TextField()),
                ('time_created', models.DateTimeField(default=django.utils.timezone.now)),
                ('time_modified', models.DateTimeField(auto_now=True)),
                ('time_refreshed', models.DateTimeField(default=django.utils.timezone.now)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='twitch', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.AlterField(
            model_name='spotifyauthorization',
            name='expires_in',
            field=models.PositiveIntegerField(),
        ),
        migrations.AlterField(
            model_name='spotifyauthorization',
            name='scope',
            field=models.TextField(),
        ),
        migrations.AlterField(
            model_name='twitchintegration',
            name='user',
            field=models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='twitch_integrations', to=settings.AUTH_USER_MODEL),
        ),
        migrations.DeleteModel(
            name='DiscordIntegration',
        ),
    ]