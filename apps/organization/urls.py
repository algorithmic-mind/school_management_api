"""مسیرهای ساختار سازمانی و آموزشی."""

from rest_framework.routers import DefaultRouter

from apps.organization.views import (
    AcademicYearViewSet,
    CalendarEventViewSet,
    CampusViewSet,
    ClassGroupViewSet,
    CourseOfferingViewSet,
    CourseViewSet,
    GradeLevelViewSet,
    ProgramCourseViewSet,
    RoomViewSet,
    ScheduleEntryViewSet,
    SchoolViewSet,
    StudyProgramViewSet,
    TermViewSet,
)

router = DefaultRouter()
router.register("schools", SchoolViewSet, basename="school")
router.register("campuses", CampusViewSet, basename="campus")
router.register("academic-years", AcademicYearViewSet, basename="academic-year")
router.register("terms", TermViewSet, basename="term")
router.register("grade-levels", GradeLevelViewSet, basename="grade-level")
router.register("programs", StudyProgramViewSet, basename="study-program")
router.register("courses", CourseViewSet, basename="course")
router.register("program-courses", ProgramCourseViewSet, basename="program-course")
router.register("rooms", RoomViewSet, basename="room")
router.register("class-groups", ClassGroupViewSet, basename="class-group")
router.register("course-offerings", CourseOfferingViewSet, basename="course-offering")
router.register("schedule-entries", ScheduleEntryViewSet, basename="schedule-entry")
router.register("calendar-events", CalendarEventViewSet, basename="calendar-event")

urlpatterns = router.urls
