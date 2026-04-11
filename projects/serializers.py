from django.conf import settings
from rest_framework import serializers

from .models import Project, Section, Task, TaskComment


class ProjectSectionSummarySerializer(serializers.ModelSerializer):
    task_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Section
        fields = ["id", "name", "order", "task_count"]


class ProjectSerializer(serializers.ModelSerializer):
    task_count = serializers.IntegerField(read_only=True)
    incomplete_count = serializers.IntegerField(read_only=True)
    overdue_count = serializers.IntegerField(read_only=True)
    sections = ProjectSectionSummarySerializer(many=True, read_only=True)

    class Meta:
        model = Project
        fields = [
            "slug",
            "name",
            "color",
            "is_active",
            "task_count",
            "incomplete_count",
            "overdue_count",
            "sections",
            "created_at",
        ]


class ProjectDetailSerializer(serializers.ModelSerializer):
    task_count = serializers.IntegerField(read_only=True)
    incomplete_count = serializers.IntegerField(read_only=True)
    overdue_count = serializers.IntegerField(read_only=True)
    sections = ProjectSectionSummarySerializer(many=True, read_only=True)

    class Meta:
        model = Project
        fields = [
            "slug",
            "name",
            "description",
            "color",
            "is_active",
            "sections",
            "task_count",
            "incomplete_count",
            "overdue_count",
            "created_at",
            "updated_at",
        ]


class ProjectWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ["name", "slug", "description", "color", "is_active"]
        extra_kwargs = {
            "slug": {"required": False, "allow_blank": True},
            "description": {"required": False},
            "color": {"required": False},
            "is_active": {"required": False},
        }


class SectionSerializer(serializers.ModelSerializer):
    project = serializers.SlugRelatedField(read_only=True, slug_field="slug")
    task_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Section
        fields = ["id", "name", "project", "order", "task_count", "created_at"]


class SectionWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Section
        fields = ["name", "order"]
        extra_kwargs = {"order": {"required": False}}


class SectionReorderSerializer(serializers.Serializer):
    order = serializers.IntegerField(min_value=0)


class TaskProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ["slug", "name"]


class TaskSectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Section
        fields = ["id", "name"]


class TaskCommentSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskComment
        fields = ["id", "text", "author", "created_at"]


class TaskSerializer(serializers.ModelSerializer):
    project = TaskProjectSerializer(read_only=True)
    section = TaskSectionSerializer(read_only=True)

    class Meta:
        model = Task
        fields = [
            "id",
            "name",
            "project",
            "section",
            "priority",
            "status",
            "due_date",
            "assignee",
            "completed",
            "tags",
            "order",
            "created_at",
        ]


class TaskDetailSerializer(TaskSerializer):
    comments = TaskCommentSerializer(many=True, read_only=True)

    class Meta(TaskSerializer.Meta):
        fields = TaskSerializer.Meta.fields + [
            "description",
            "completed_at",
            "comments",
            "updated_at",
        ]


class TaskWriteSerializer(serializers.ModelSerializer):
    project_slug = serializers.SlugRelatedField(
        source="project",
        slug_field="slug",
        queryset=Project.objects.all(),
    )
    section_id = serializers.PrimaryKeyRelatedField(
        source="section",
        queryset=Section.objects.all(),
        allow_null=True,
        required=False,
    )

    class Meta:
        model = Task
        fields = [
            "project_slug",
            "section_id",
            "name",
            "description",
            "priority",
            "status",
            "due_date",
            "assignee",
            "order",
            "tags",
        ]
        extra_kwargs = {
            "description": {"required": False},
            "priority": {"required": False},
            "status": {"required": False},
            "due_date": {"required": False, "allow_null": True},
            "assignee": {"required": False},
            "order": {"required": False},
            "tags": {"required": False},
        }

    def validate_tags(self, value: list) -> list[str]:
        if not isinstance(value, list) or any(not isinstance(tag, str) for tag in value):
            raise serializers.ValidationError("Tags must be a list of strings.")
        return value

    def validate(self, attrs: dict) -> dict:
        project = attrs.get("project", getattr(self.instance, "project", None))
        section = attrs.get("section", getattr(self.instance, "section", None))

        if section and project and section.project_id != project.id:
            raise serializers.ValidationError({"section_id": "Section must belong to the selected project."})

        max_tasks = getattr(settings, "PROJECTS_MAX_TASKS_PER_PROJECT", 0)
        if max_tasks and project:
            queryset = Task.objects.filter(project=project)
            if self.instance:
                queryset = queryset.exclude(pk=self.instance.pk)
            if queryset.count() >= max_tasks:
                raise serializers.ValidationError(
                    {"project_slug": "This project has reached the configured task limit."}
                )

        return attrs


class TaskMoveSerializer(serializers.Serializer):
    project_slug = serializers.SlugRelatedField(
        slug_field="slug",
        queryset=Project.objects.all(),
        required=False,
    )
    section_id = serializers.PrimaryKeyRelatedField(
        queryset=Section.objects.all(),
        required=False,
        allow_null=True,
    )

    def validate(self, attrs: dict) -> dict:
        task: Task = self.context["task"]
        project = attrs.get("project_slug", task.project)
        section = attrs.get("section_id", serializers.empty)

        if "project_slug" not in attrs and section is serializers.empty:
            raise serializers.ValidationError("Provide project_slug, section_id, or both.")

        if section is not serializers.empty and section is not None and section.project_id != project.id:
            if "project_slug" in attrs and project.id != task.project_id:
                attrs["section_id"] = None
            else:
                raise serializers.ValidationError({"section_id": "Section must belong to the selected project."})

        return attrs


class TaskCommentWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskComment
        fields = ["text", "author"]
        extra_kwargs = {"author": {"required": False}}
