from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .filters import apply_task_filters, upcoming_tasks_queryset
from .models import Project, Section, Task, TaskComment
from .serializers import (
    ProjectDetailSerializer,
    ProjectSerializer,
    ProjectWriteSerializer,
    SectionReorderSerializer,
    SectionSerializer,
    SectionWriteSerializer,
    TaskCommentSerializer,
    TaskCommentWriteSerializer,
    TaskDetailSerializer,
    TaskMoveSerializer,
    TaskSerializer,
    TaskWriteSerializer,
)


def project_queryset():
    today = timezone.localdate()
    sections_queryset = Section.objects.annotate(task_count=Count("tasks")).order_by("order", "id")
    return (
        Project.objects.annotate(
            task_count=Count("tasks", distinct=True),
            incomplete_count=Count("tasks", filter=Q(tasks__completed=False), distinct=True),
            overdue_count=Count(
                "tasks",
                filter=Q(tasks__completed=False, tasks__due_date__lt=today, tasks__due_date__isnull=False),
                distinct=True,
            ),
        )
        .prefetch_related(Prefetch("sections", queryset=sections_queryset))
        .order_by("name", "id")
    )


def task_base_queryset():
    return Task.objects.select_related("project", "section").prefetch_related("comments")


# NockCC-specific adaptation: the plugin's stock mixin only accepts DRF
# session + token auth, but the rest of NockCC's API (brain, diary, etc.)
# also accepts an `X-API-Key` header via `core.auth.require_brain_access`.
# To keep `curl -H "X-API-Key: ..."` working uniformly across
# `/api/brain/*` and `/api/pm/*`, we import NockCC's DRF-compatible
# api-key backend and include it in the default authentication chain.
#
# The import is wrapped in try/except so the plugin still runs in a host
# project without a `core/auth.py` module — if the import fails we fall
# back to the stock (TokenAuthentication, SessionAuthentication) pair.
# Host projects wanting their own key scheme can drop this adaptation
# entirely and configure `authentication_classes` their own way.
try:
    from core.auth import NockCCApiKeyAuthentication  # noqa: PLC0415 — intentional

    _DEFAULT_AUTHENTICATION_CLASSES = [
        NockCCApiKeyAuthentication,
        TokenAuthentication,
        SessionAuthentication,
    ]
except ImportError:  # pragma: no cover — only hit outside NockCC
    _DEFAULT_AUTHENTICATION_CLASSES = [TokenAuthentication, SessionAuthentication]


class ProjectsAPIViewMixin:
    authentication_classes = _DEFAULT_AUTHENTICATION_CLASSES
    permission_classes = [IsAuthenticated]


class ProjectListCreateView(ProjectsAPIViewMixin, generics.ListCreateAPIView):
    def get_queryset(self):
        return project_queryset().filter(is_active=True, is_archived=False)

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ProjectWriteSerializer
        return ProjectSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        project = serializer.save()
        output = ProjectDetailSerializer(project_queryset().get(pk=project.pk))
        return Response(output.data, status=status.HTTP_201_CREATED)


class ProjectDetailView(ProjectsAPIViewMixin, generics.RetrieveUpdateDestroyAPIView):
    lookup_field = "slug"

    def get_queryset(self):
        return project_queryset()

    def get_serializer_class(self):
        if self.request.method in {"PUT", "PATCH"}:
            return ProjectWriteSerializer
        return ProjectDetailSerializer

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        output = ProjectDetailSerializer(project_queryset().get(pk=instance.pk))
        return Response(output.data)

    def perform_destroy(self, instance: Project) -> None:
        instance.is_archived = True
        instance.is_active = False
        instance.save(update_fields=["is_archived", "is_active", "updated_at"])


class ProjectSectionListCreateView(ProjectsAPIViewMixin, generics.ListCreateAPIView):
    serializer_class = SectionSerializer

    def get_project(self) -> Project:
        return get_object_or_404(Project.objects.all(), slug=self.kwargs["slug"])

    def get_queryset(self):
        return (
            Section.objects.filter(project=self.get_project())
            .annotate(task_count=Count("tasks"))
            .order_by("order", "id")
        )

    def get_serializer_class(self):
        if self.request.method == "POST":
            return SectionWriteSerializer
        return SectionSerializer

    def create(self, request, *args, **kwargs):
        project = self.get_project()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        section = serializer.save(project=project)
        output = SectionSerializer(
            Section.objects.annotate(task_count=Count("tasks")).get(pk=section.pk)
        )
        return Response(output.data, status=status.HTTP_201_CREATED)


class SectionDetailView(ProjectsAPIViewMixin, generics.RetrieveUpdateDestroyAPIView):
    def get_serializer_class(self):
        if self.request.method in {"PUT", "PATCH"}:
            return SectionWriteSerializer
        return SectionSerializer

    def get_queryset(self):
        return Section.objects.annotate(task_count=Count("tasks")).select_related("project")

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        output = SectionSerializer(Section.objects.annotate(task_count=Count("tasks")).get(pk=instance.pk))
        return Response(output.data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        with transaction.atomic():
            instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SectionReorderView(ProjectsAPIViewMixin, APIView):
    def post(self, request, pk: int):
        section = get_object_or_404(Section.objects.all(), pk=pk)
        serializer = SectionReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        section.order = serializer.validated_data["order"]
        section.save(update_fields=["order", "updated_at"])
        output = SectionSerializer(Section.objects.annotate(task_count=Count("tasks")).get(pk=section.pk))
        return Response(output.data)


class TaskListCreateView(ProjectsAPIViewMixin, generics.ListCreateAPIView):
    def get_queryset(self):
        queryset = task_base_queryset()
        return apply_task_filters(queryset, self.request.query_params)

    def get_serializer_class(self):
        if self.request.method == "POST":
            return TaskWriteSerializer
        return TaskSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        task = serializer.save()
        output = TaskDetailSerializer(task_base_queryset().get(pk=task.pk))
        return Response(output.data, status=status.HTTP_201_CREATED)


class TaskDetailView(ProjectsAPIViewMixin, generics.RetrieveUpdateDestroyAPIView):
    def get_serializer_class(self):
        if self.request.method in {"PUT", "PATCH"}:
            return TaskWriteSerializer
        return TaskDetailSerializer

    def get_queryset(self):
        return task_base_queryset()

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        output = TaskDetailSerializer(task_base_queryset().get(pk=instance.pk))
        return Response(output.data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class TaskCompleteView(ProjectsAPIViewMixin, APIView):
    def post(self, request, pk: int):
        with transaction.atomic():
            # Use get_object_or_404 so a missing pk returns 404, not 500.
            task = get_object_or_404(Task.objects.select_for_update(), pk=pk)
            task.status = Task.STATUS_DONE
            task.save()
        return Response(TaskDetailSerializer(task_base_queryset().get(pk=pk)).data)


class TaskReopenView(ProjectsAPIViewMixin, APIView):
    def post(self, request, pk: int):
        with transaction.atomic():
            task = get_object_or_404(Task.objects.select_for_update(), pk=pk)
            task.status = Task.STATUS_TODO
            task.save()
        return Response(TaskDetailSerializer(task_base_queryset().get(pk=pk)).data)


class TaskMoveView(ProjectsAPIViewMixin, APIView):
    def post(self, request, pk: int):
        with transaction.atomic():
            task = get_object_or_404(Task.objects.select_for_update(), pk=pk)
            serializer = TaskMoveSerializer(data=request.data, context={"task": task})
            serializer.is_valid(raise_exception=True)

            if "project_slug" in serializer.validated_data:
                task.project = serializer.validated_data["project_slug"]
                task.section = None

            if "section_id" in serializer.validated_data:
                task.section = serializer.validated_data["section_id"]

            task.save()

        return Response(TaskDetailSerializer(task_base_queryset().get(pk=pk)).data)


class TaskCommentListCreateView(ProjectsAPIViewMixin, generics.ListCreateAPIView):
    def get_task(self) -> Task:
        return get_object_or_404(Task.objects.all(), pk=self.kwargs["pk"])

    def get_queryset(self):
        return self.get_task().comments.order_by("-created_at", "-id")

    def get_serializer_class(self):
        if self.request.method == "POST":
            return TaskCommentWriteSerializer
        return TaskCommentSerializer

    def create(self, request, *args, **kwargs):
        task = self.get_task()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        comment = serializer.save(task=task)
        return Response(TaskCommentSerializer(comment).data, status=status.HTTP_201_CREATED)


class CommentDetailView(ProjectsAPIViewMixin, generics.DestroyAPIView):
    def get_queryset(self):
        return TaskComment.objects.all()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class TaskDashboardView(ProjectsAPIViewMixin, APIView):
    def get(self, request):
        today = timezone.localdate()
        tasks = Task.objects.select_related("project")
        incomplete = tasks.filter(completed=False)
        projects = (
            Project.objects.filter(is_archived=False)
            .annotate(
                incomplete=Count("tasks", filter=Q(tasks__completed=False), distinct=True),
                overdue=Count(
                    "tasks",
                    filter=Q(tasks__completed=False, tasks__due_date__lt=today, tasks__due_date__isnull=False),
                    distinct=True,
                ),
            )
            .order_by("name", "id")
        )

        payload = {
            "total_tasks": tasks.count(),
            "incomplete_tasks": incomplete.count(),
            "overdue_tasks": incomplete.filter(due_date__lt=today, due_date__isnull=False).count(),
            "completed_today": tasks.filter(completed=True, completed_at__date=today).count(),
            "by_project": [
                {
                    "slug": project.slug,
                    "name": project.name,
                    "incomplete": project.incomplete,
                    "overdue": project.overdue,
                }
                for project in projects
            ],
            "by_priority": {
                priority: incomplete.filter(priority=priority).count()
                for priority, _label in Task.PRIORITY_CHOICES
            },
        }
        return Response(payload)


class TaskOverdueView(ProjectsAPIViewMixin, APIView):
    def get(self, request):
        today = timezone.localdate()
        queryset = (
            task_base_queryset()
            .filter(completed=False, due_date__lt=today, due_date__isnull=False)
            .order_by("due_date", "id")
        )
        return Response(TaskSerializer(queryset, many=True).data)


class TaskTodayView(ProjectsAPIViewMixin, APIView):
    def get(self, request):
        today = timezone.localdate()
        queryset = task_base_queryset().filter(due_date=today).order_by("id")
        return Response(TaskSerializer(queryset, many=True).data)


class TaskUpcomingView(ProjectsAPIViewMixin, APIView):
    def get(self, request):
        try:
            days = int(request.query_params.get("days", 7))
        except (TypeError, ValueError):
            days = 7

        queryset = upcoming_tasks_queryset(task_base_queryset(), days).order_by("due_date", "id")
        return Response(TaskSerializer(queryset, many=True).data)
