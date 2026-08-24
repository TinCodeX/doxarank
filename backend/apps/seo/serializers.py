from django.utils import timezone
from rest_framework import serializers
from .models import (
    Keyword, KeywordRanking, SearchEngine, Country, Language, Device,
    SiteAudit, AuditIssue, AuditStatus, IssueSeverity,
    SearchConsoleConnection, SearchConsolePermission, SearchConsoleSyncStatus
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


