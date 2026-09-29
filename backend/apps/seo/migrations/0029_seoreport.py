from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('seo', '0028_alter_competitorsnapshot_options_recommendation'),
    ]

    operations = [
        migrations.CreateModel(
            name='SEOReport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(default='SEO Performance & Technical Audit Report', help_text='Report title heading (e.g. "Monthly Executive SEO Report").', max_length=255)),
                ('client_name', models.CharField(blank=True, default='', help_text='Optional client or company name for white-label branding.', max_length=255)),
                ('status', models.CharField(choices=[('PENDING', 'Pending'), ('RUNNING', 'Running'), ('COMPLETED', 'Completed'), ('FAILED', 'Failed')], db_index=True, default='PENDING', help_text='Execution status of the PDF generation.', max_length=30)),
                ('file_path', models.CharField(blank=True, default='', help_text='Internal relative path to the generated PDF artifact (never exposed to API).', max_length=512)),
                ('file_size_bytes', models.PositiveIntegerField(default=0, help_text='Size of the generated PDF in bytes.')),
                ('celery_task_id', models.CharField(blank=True, help_text='Celery task ID tracking the background PDF generation job.', max_length=255, null=True)),
                ('summary_data', models.JSONField(blank=True, default=dict, help_text='Normalized snapshot summary of the report metrics at time of generation.')),
                ('error_message', models.TextField(blank=True, default='', help_text='Error details if the report generation failed.')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, help_text='Timestamp when the report generation was requested.')),
                ('completed_at', models.DateTimeField(blank=True, help_text='Timestamp when PDF generation finished successfully.', null=True)),
                ('generated_by', models.ForeignKey(blank=True, help_text='The user who requested/generated this report.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='generated_seo_reports', to=settings.AUTH_USER_MODEL)),
                ('project', models.ForeignKey(help_text='The project/website this SEO report was generated for.', on_delete=django.db.models.deletion.CASCADE, related_name='reports', to='projects.project')),
            ],
            options={
                'verbose_name': 'SEO report',
                'verbose_name_plural': 'SEO reports',
                'db_table': 'seo_reports',
                'ordering': ['-created_at'],
                'indexes': [
                    models.Index(fields=['project', '-created_at'], name='seo_rep_proj_created_idx'),
                    models.Index(fields=['status'], name='seo_rep_status_idx'),
                ],
            },
        ),
    ]
