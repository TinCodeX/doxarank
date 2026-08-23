from django.utils import timezone
from rest_framework import serializers
from .models import Keyword, KeywordRanking, SearchEngine, Country, Language, Device
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
