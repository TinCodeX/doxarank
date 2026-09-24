from django.db import migrations
from django.utils import timezone


def seed_plans_and_subscriptions(apps, schema_editor):
    Plan = apps.get_model('subscriptions', 'Plan')
    Subscription = apps.get_model('subscriptions', 'Subscription')
    User = apps.get_model('users', 'User')

    # Seed the 3 foundational plans
    plans_data = [
        {
            'code': 'FREE',
            'name': 'Free',
            'monthly_price': 0.00,
            'currency': 'ETB',
            'max_projects': 1,
            'max_keywords': 3,
            'basic_tool_daily_limit': 5,
            'features': ['BASIC_SEO_TOOLS'],
            'is_active': True,
        },
        {
            'code': 'STARTER',
            'name': 'Starter',
            'monthly_price': 1500.00,
            'currency': 'ETB',
            'max_projects': 3,
            'max_keywords': 50,
            'basic_tool_daily_limit': 0,
            'features': [
                'BASIC_SEO_TOOLS',
                'RANK_TRACKING',
                'GSC',
                'GA4',
                'CLARITY',
                'GTM',
                'TECHNICAL_CRAWLER',
            ],
            'is_active': True,
        },
        {
            'code': 'AGENCY',
            'name': 'Agency',
            'monthly_price': 6000.00,
            'currency': 'ETB',
            'max_projects': 20,
            'max_keywords': 500,
            'basic_tool_daily_limit': 0,
            'features': [
                'BASIC_SEO_TOOLS',
                'RANK_TRACKING',
                'GSC',
                'GA4',
                'CLARITY',
                'GTM',
                'TECHNICAL_CRAWLER',
                'COMPETITOR_SNAPSHOTS',
                'WHITE_LABEL_REPORTS',
            ],
            'is_active': True,
        },
    ]

    created_plans = {}
    for p in plans_data:
        plan, _ = Plan.objects.get_or_create(code=p['code'], defaults=p)
        created_plans[p['code']] = plan

    free_plan = created_plans['FREE']

    # For any existing users in the database, attach a FREE subscription
    now = timezone.now()
    for user in User.objects.all():
        if not Subscription.objects.filter(user=user).exists():
            Subscription.objects.create(
                user=user,
                plan=free_plan,
                status='active',
                started_at=now,
                current_period_end=None,
            )


def rollback_plans(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('subscriptions', '0001_initial'),
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_plans_and_subscriptions, rollback_plans),
    ]
