from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='historycheckcounterparty',
            name='error_text',
            field=models.TextField(blank=True, default='', help_text='Технический текст ошибки интеграции. Пользователям не показывается.', verbose_name='Текст ошибки'),
        ),
        migrations.AlterField(
            model_name='historycheckcounterparty',
            name='result',
            field=models.TextField(blank=True, default='', verbose_name='Результат проверки (JSON)'),
        ),
    ]
