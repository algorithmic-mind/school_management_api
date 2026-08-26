"""مسیرهای منابع انسانی."""

from rest_framework.routers import DefaultRouter

from apps.hr.views import (
    EmployeeAssignmentViewSet,
    EmployeeAttendanceViewSet,
    EmployeeViewSet,
    EmploymentContractViewSet,
    LeaveRequestViewSet,
    OrgUnitViewSet,
    PayrollRunViewSet,
    PayslipViewSet,
    PositionViewSet,
    TeacherProfileViewSet,
    TeacherQualificationViewSet,
    TeachingAssignmentViewSet,
    WorkShiftViewSet,
)

router = DefaultRouter()
router.register("org-units", OrgUnitViewSet, basename="org-unit")
router.register("positions", PositionViewSet, basename="position")
router.register("employees", EmployeeViewSet, basename="employee")
router.register("contracts", EmploymentContractViewSet, basename="contract")
router.register("assignments", EmployeeAssignmentViewSet, basename="employee-assignment")
router.register("teachers", TeacherProfileViewSet, basename="teacher-profile")
router.register("qualifications", TeacherQualificationViewSet, basename="qualification")
router.register("teaching-assignments", TeachingAssignmentViewSet, basename="teaching-assignment")
router.register("shifts", WorkShiftViewSet, basename="work-shift")
router.register("attendances", EmployeeAttendanceViewSet, basename="employee-attendance")
router.register("leaves", LeaveRequestViewSet, basename="leave-request")
router.register("payroll-runs", PayrollRunViewSet, basename="payroll-run")
router.register("payslips", PayslipViewSet, basename="payslip")

urlpatterns = router.urls
