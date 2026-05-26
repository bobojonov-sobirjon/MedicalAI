from __future__ import annotations

from django.db.models import Q

from .models import CustomUser, FamilyLink


def family_member_ids(owner: CustomUser) -> list[int]:
    return list(FamilyLink.objects.filter(owner=owner).values_list("member_id", flat=True))


def allowed_profile_ids(owner: CustomUser) -> set[int]:
    return {owner.pk, *family_member_ids(owner)}


def allowed_profiles_qs(owner: CustomUser):
    return CustomUser.objects.filter(pk__in=allowed_profile_ids(owner))


def resolve_profile_user(owner: CustomUser, profile_user_id: int | None) -> CustomUser | None:
    """Return profile user if owner may act on their behalf; default is owner."""
    if profile_user_id is None:
        return owner
    if profile_user_id == owner.pk:
        return owner
    member = CustomUser.objects.filter(pk=profile_user_id).first()
    if not member:
        return None
    if FamilyLink.objects.filter(owner=owner, member=member).exists():
        return member
    return None


def family_link_for(owner: CustomUser, member_id: int) -> FamilyLink | None:
    return FamilyLink.objects.filter(owner=owner, member_id=member_id).select_related("member").first()
