from django.utils import timezone
from rest_framework import serializers
from .models import (
    Keyword, KeywordRanking, SearchEngine, Country, Language, Device,
    SiteAudit, AuditIssue, AuditStatus, IssueSeverity,
    SearchConsoleConnection, SearchConsolePermission, SearchConsoleSyncStatus,
    SearchAnalyticsData,
    SEOInsight, InsightSeverity, InsightStatus, InsightSource, InsightType,
    SEORecommendation, RecommendationType, RecommendationPriority, RecommendationStatus
)
from apps.projects.models import Project



class KeywordSerializer(serializers.ModelSerializer):
    """
    Serializer for Keyword model.
    Enforces strict ownership validation on project selection and input hygiene.
    """
    project_name = serializers.CharField(source='project.name', read_only=True)
    project_website_url = serializers.CharField(source='project.website_url', read_only=True)

    class Meta:
        model = Keyword
        fields = (
            'id',
            'project',
            'project_name',
            'project_website_url',
            'keyword',
            'search_engine',
            'country',
            'language',
            'device',
            'is_active',
            'created_at',
            'updated_at'
        )
        read_only_fields = ('id', 'project_name', 'project_website_url', 'created_at', 'updated_at')

    def validate_keyword(self, value):
        trimmed = value.strip()
        if not trimmed:
            raise serializers.ValidationError("Keyword cannot be blank.")
        if len(trimmed) < 2:
            raise serializers.ValidationError("Keyword must be at least 2 characters.")
        if len(trimmed) > 255:
            raise serializers.ValidationError("Keyword cannot exceed 255 characters.")
        return trimmed

    def validate_project(self, value):
        """
        Critical security boundary:
        Ensure the target project is owned by the currently authenticated user.
        """
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            if value.owner != request.user:
                raise serializers.ValidationError("You do not have permission to add keywords to this project.")
        return value

    def validate(self, attrs):
        project = attrs.get('project') or (self.instance.project if self.instance else None)
        keyword = attrs.get('keyword') or (self.instance.keyword if self.instance else None)
        search_engine = attrs.get('search_engine') or (self.instance.search_engine if self.instance else SearchEngine.GOOGLE)
        country = attrs.get('country') or (self.instance.country if self.instance else Country.ET)
        language = attrs.get('language') or (self.instance.language if self.instance else Language.EN)
        device = attrs.get('device') or (self.instance.device if self.instance else Device.DESKTOP)

        if project and keyword:
            qs = Keyword.objects.filter(
                project=project,
                keyword__iexact=keyword.strip(),
                search_engine=search_engine,
                country=country,
                language=language,
                device=device
            )
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError({
                    'keyword': f"The keyword '{keyword}' is already being tracked for this project under the selected configuration."
                })

        return attrs


class KeywordRankingSerializer(serializers.ModelSerializer):
    """
    Serializer for KeywordRanking model.
    Validates ownership via keyword.project.owner and enforces position/URL hygiene.
    """
    keyword_name = serializers.CharField(source='keyword.keyword', read_only=True)
    project_id = serializers.IntegerField(source='keyword.project.id', read_only=True)
    project_name = serializers.CharField(source='keyword.project.name', read_only=True)

    class Meta:
        model = KeywordRanking
        fields = (
            'id',
            'keyword',
            'keyword_name',
            'project_id',
            'project_name',
            'position',
            'ranking_url',
            'search_engine',
            'country',
            'language',
            'device',
            'recorded_at',
            'created_at'
        )
        read_only_fields = ('id', 'keyword_name', 'project_id', 'project_name', 'created_at')

    def validate_position(self, value):
        if value < 1:
            raise serializers.ValidationError("Position must be a positive integer greater than or equal to 1.")
        if value > 1000:
            raise serializers.ValidationError("Position cannot exceed 1000.")
        return value

    def validate_keyword(self, value):
        """
        Critical security boundary:
        Ensure the keyword's parent project is owned by the currently authenticated user.
        """
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            if value.project.owner != request.user:
                raise serializers.ValidationError("You do not have permission to record rankings for a keyword you do not own.")
        return value

    def validate(self, attrs):
        keyword = attrs.get('keyword') or (self.instance.keyword if self.instance else None)
        search_engine = attrs.get('search_engine') or (self.instance.search_engine if self.instance else getattr(keyword, 'search_engine', SearchEngine.GOOGLE))
        country = attrs.get('country') or (self.instance.country if self.instance else getattr(keyword, 'country', Country.ET))
        language = attrs.get('language') or (self.instance.language if self.instance else getattr(keyword, 'language', Language.EN))
        device = attrs.get('device') or (self.instance.device if self.instance else getattr(keyword, 'device', Device.DESKTOP))
        recorded_at = attrs.get('recorded_at') or (self.instance.recorded_at if self.instance else timezone.now())

        if keyword:
            qs = KeywordRanking.objects.filter(
                keyword=keyword,
                search_engine=search_engine,
                country=country,
                language=language,
                device=device,
                recorded_at=recorded_at
            )
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    "A ranking observation with this exact configuration and timestamp already exists."
                )

        return attrs


class SiteAuditSerializer(serializers.ModelSerializer):
    """
    Serializer for SiteAudit model.
    Enforces project ownership verification and validates score/completion boundaries.
    """
    project_name = serializers.CharField(source='project.name', read_only=True)
    project_website_url = serializers.CharField(source='project.website_url', read_only=True)
    issues_count = serializers.IntegerField(source='issues.count', read_only=True)

    class Meta:
        model = SiteAudit
        fields = (
            'id',
            'project',
            'project_name',
            'project_website_url',
            'status',
            'score',
            'started_at',
            'completed_at',
            'created_at',
            'updated_at',
            'error_message',
            'issues_count'
        )
        read_only_fields = ('id', 'project_name', 'project_website_url', 'created_at', 'updated_at', 'issues_count')

    def validate_project(self, value):
        """
        Critical security boundary:
        Ensure the target project is owned by the currently authenticated user.
        """
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            if value.owner != request.user:
                raise serializers.ValidationError("You do not have permission to create site audits for this project.")
        return value

    def validate_score(self, value):
        if value is not None:
            if value < 0 or value > 100:
                raise serializers.ValidationError("Score must be an integer between 0 and 100.")
        return value

    def validate(self, attrs):
        score = attrs.get('score') if 'score' in attrs else (self.instance.score if self.instance else None)
        if score is not None and (score < 0 or score > 100):
            raise serializers.ValidationError({'score': "Score must be an integer between 0 and 100."})
        return attrs


class AuditIssueSerializer(serializers.ModelSerializer):
    """
    Serializer for AuditIssue model.
    Enforces audit ownership verification via audit.project.owner.
    """
    project_id = serializers.IntegerField(source='audit.project.id', read_only=True)
    project_name = serializers.CharField(source='audit.project.name', read_only=True)

    class Meta:
        model = AuditIssue
        fields = (
            'id',
            'audit',
            'project_id',
            'project_name',
            'issue_type',
            'severity',
            'title',
            'description',
            'page_url',
            'recommendation',
            'created_at'
        )
        read_only_fields = ('id', 'project_id', 'project_name', 'created_at')

    def validate_audit(self, value):
        """
        Critical security boundary:
        Ensure the target audit belongs to a project owned by the currently authenticated user.
        """
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            if value.project.owner != request.user:
                raise serializers.ValidationError("You do not have permission to add issues to an audit you do not own.")
        return value

    def validate_issue_type(self, value):
        trimmed = value.strip()
        if not trimmed:
            raise serializers.ValidationError("Issue type cannot be blank.")
        return trimmed

    def validate_title(self, value):
        trimmed = value.strip()
        if not trimmed:
            raise serializers.ValidationError("Title cannot be blank.")
        return trimmed


class SearchConsoleConnectionSerializer(serializers.ModelSerializer):
    """
    Serializer for SearchConsoleConnection model.
    Enforces strict project ownership validation and property URL hygiene.
    """
    project_name = serializers.CharField(source='project.name', read_only=True)
    project_website_url = serializers.CharField(source='project.website_url', read_only=True)

    class Meta:
        model = SearchConsoleConnection
        fields = (
            'id',
            'project',
            'project_name',
            'project_website_url',
            'property_url',
            'permission_level',
            'is_connected',
            'connected_at',
            'last_synced_at',
            'sync_status',
            'error_message',
            'created_at',
            'updated_at'
        )
        read_only_fields = ('id', 'project_name', 'project_website_url', 'connected_at', 'created_at', 'updated_at')

    def validate_property_url(self, value):
        trimmed = value.strip()
        if not trimmed:
            raise serializers.ValidationError("Property URL cannot be blank.")
        if len(trimmed) > 500:
            raise serializers.ValidationError("Property URL cannot exceed 500 characters.")
        return trimmed

    def validate_project(self, value):
        """
        Critical security boundary:
        Ensure the target project is owned by the currently authenticated user.
        """
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            if value.owner != request.user:
                raise serializers.ValidationError("You do not have permission to connect Search Console to this project.")
        return value

    def validate(self, attrs):
        project = attrs.get('project') or (self.instance.project if self.instance else None)
        if project and not self.instance:
            if SearchConsoleConnection.objects.filter(project=project).exists():
                raise serializers.ValidationError({
                    'project': "A Search Console connection already exists for this project."
                })
        return attrs


class SearchAnalyticsDataSerializer(serializers.ModelSerializer):
    """
    Serializer for SearchAnalyticsData model.
    Validates ownership via connection.project.owner, validates metric boundaries,
    and prevents duplicate observations.
    """
    project_id = serializers.IntegerField(source='connection.project.id', read_only=True)
    project_name = serializers.CharField(source='connection.project.name', read_only=True)
    property_url = serializers.CharField(source='connection.property_url', read_only=True)

    class Meta:
        model = SearchAnalyticsData
        fields = (
            'id',
            'connection',
            'project_id',
            'project_name',
            'property_url',
            'date',
            'query',
            'page',
            'country',
            'device',
            'search_appearance',
            'clicks',
            'impressions',
            'ctr',
            'position',
            'created_at',
            'updated_at'
        )
        read_only_fields = (
            'id',
            'project_id',
            'project_name',
            'property_url',
            'created_at',
            'updated_at'
        )

    def validate_connection(self, value):
        """
        Critical security boundary:
        Ensure the target SearchConsoleConnection belongs to a project owned by the authenticated user.
        """
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            if value.project.owner != request.user:
                raise serializers.ValidationError(
                    "You do not have permission to add Search Analytics data to a connection you do not own."
                )
        return value

    def validate_clicks(self, value):
        if value < 0:
            raise serializers.ValidationError("Clicks cannot be negative.")
        return value

    def validate_impressions(self, value):
        if value < 0:
            raise serializers.ValidationError("Impressions cannot be negative.")
        return value

    def validate_ctr(self, value):
        if value < 0 or value > 100:
            raise serializers.ValidationError("CTR must be between 0 and 100 (or 0.0 and 1.0).")
        return value

    def validate_position(self, value):
        if value < 0:
            raise serializers.ValidationError("Average position cannot be negative.")
        if value > 1000:
            raise serializers.ValidationError("Average position cannot exceed 1000.")
        return value

    def validate(self, attrs):
        connection = attrs.get('connection') or (self.instance.connection if self.instance else None)
        date = attrs.get('date') or (self.instance.date if self.instance else None)
        query = attrs.get('query') if 'query' in attrs else (self.instance.query if self.instance else '')
        page = attrs.get('page') if 'page' in attrs else (self.instance.page if self.instance else '')
        country = attrs.get('country') if 'country' in attrs else (self.instance.country if self.instance else '')
        device = attrs.get('device') if 'device' in attrs else (self.instance.device if self.instance else '')
        search_appearance = attrs.get('search_appearance') if 'search_appearance' in attrs else (self.instance.search_appearance if self.instance else '')

        # Also validate clicks / impressions if both provided
        clicks = attrs.get('clicks') if 'clicks' in attrs else (self.instance.clicks if self.instance else 0)
        impressions = attrs.get('impressions') if 'impressions' in attrs else (self.instance.impressions if self.instance else 0)
        if clicks < 0:
            raise serializers.ValidationError({'clicks': "Clicks cannot be negative."})
        if impressions < 0:
            raise serializers.ValidationError({'impressions': "Impressions cannot be negative."})

        # Check for duplicate observation
        if connection and date:
            qs = SearchAnalyticsData.objects.filter(
                connection=connection,
                date=date,
                query=query,
                page=page,
                country=country,
                device=device,
                search_appearance=search_appearance
            )
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    "A Search Analytics record with this exact combination (connection, date, query, page, country, device, search_appearance) already exists."
                )

        return attrs


class SearchConsoleSyncRequestSerializer(serializers.Serializer):
    """
    Serializer for triggering a Google Search Console synchronization.
    """
    project_id = serializers.IntegerField(required=False, help_text="ID of the project to synchronize.")
    connection_id = serializers.IntegerField(required=False, help_text="ID of the connection to synchronize.")
    start_date = serializers.DateField(required=False, help_text="Start date for Search Analytics query (defaults to 28 days ago).")
    end_date = serializers.DateField(required=False, help_text="End date for Search Analytics query (defaults to today).")

    def validate(self, attrs):
        start_date = attrs.get('start_date')
        end_date = attrs.get('end_date')
        if start_date and end_date and start_date > end_date:
            raise serializers.ValidationError("start_date cannot be after end_date.")
        return attrs


class SEOInsightSerializer(serializers.ModelSerializer):
    """
    Serializer for SEOInsight model.
    Enforces project ownership and handles lifecycle status timestamps.
    """
    project_name = serializers.CharField(source='project.name', read_only=True)
    related_keyword_name = serializers.CharField(source='related_keyword.keyword', read_only=True, default=None)

    class Meta:
        model = SEOInsight
        fields = (
            'id',
            'project',
            'project_name',
            'fingerprint',
            'insight_type',
            'severity',
            'title',
            'description',
            'recommendation',
            'status',
            'source',
            'related_keyword',
            'related_keyword_name',
            'related_url',
            'metadata',
            'detected_at',
            'resolved_at',
            'created_at',
            'updated_at'
        )
        read_only_fields = (
            'id',
            'project_name',
            'related_keyword_name',
            'created_at',
            'updated_at'
        )

    def validate_project(self, value):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            if value.owner != request.user:
                raise serializers.ValidationError("You do not have permission to attach insights to this project.")
        return value

    def update(self, instance, validated_data):
        new_status = validated_data.get('status', instance.status)
        if new_status == InsightStatus.RESOLVED and instance.status != InsightStatus.RESOLVED:
            validated_data['resolved_at'] = timezone.now()
        elif new_status != InsightStatus.RESOLVED and instance.status == InsightStatus.RESOLVED:
            validated_data['resolved_at'] = None

        return super().update(instance, validated_data)


class SEOInsightAnalyzeRequestSerializer(serializers.Serializer):
    """
    Serializer for validating SEO Intelligence analysis requests.
    """
    project_id = serializers.IntegerField(
        required=True,
        help_text="ID of the project to run SEO intelligence analysis on."
    )

    def validate_project_id(self, value):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            if not Project.objects.filter(id=value, owner=request.user).exists():
                raise serializers.ValidationError("Project does not exist or you do not have permission to analyze it.")
        return value


class SEOInsightStatusUpdateSerializer(serializers.Serializer):
    """
    Serializer for updating insight lifecycle status.
    """
    status = serializers.ChoiceField(
        choices=InsightStatus.choices,
        help_text="Target status: open, dismissed, or resolved."
    )


class SEORecommendationSerializer(serializers.ModelSerializer):
    """
    Serializer for SEORecommendation model.
    Enforces project ownership and exposes rich context from the originating insight.
    """
    project_name = serializers.CharField(source='project.name', read_only=True)
    insight_title = serializers.CharField(source='insight.title', read_only=True)
    insight_severity = serializers.CharField(source='insight.severity', read_only=True)
    insight_type = serializers.CharField(source='insight.insight_type', read_only=True)

    class Meta:
        model = SEORecommendation
        fields = (
            'id',
            'project',
            'project_name',
            'insight',
            'insight_title',
            'insight_severity',
            'insight_type',
            'recommendation_type',
            'title',
            'summary',
            'explanation',
            'priority',
            'recommended_action',
            'expected_impact',
            'affected_url',
            'affected_keyword',
            'generated_content',
            'status',
            'created_at',
            'updated_at'
        )
        read_only_fields = (
            'id',
            'project_name',
            'insight_title',
            'insight_severity',
            'insight_type',
            'created_at',
            'updated_at'
        )

    def validate_project(self, value):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            if value.owner != request.user:
                raise serializers.ValidationError("You do not have permission to create recommendations for this project.")
        return value


class SEORecommendationGenerateRequestSerializer(serializers.Serializer):
    """
    Serializer for triggering AI recommendation generation for a project or specific insights.
    """
    project_id = serializers.IntegerField(
        required=True,
        help_text="ID of the project to generate AI recommendations for."
    )
    insight_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        default=list,
        help_text="Optional list of specific insight IDs to generate recommendations for."
    )

    def validate_project_id(self, value):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            if not Project.objects.filter(id=value, owner=request.user).exists():
                raise serializers.ValidationError("Project does not exist or you do not have permission to access it.")
        return value






