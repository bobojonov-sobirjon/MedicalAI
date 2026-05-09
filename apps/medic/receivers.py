from __future__ import annotations

from decimal import Decimal

from django.db.models import Avg
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.catalog.models import Drug

from .models import DrugUserStarRating


def _refresh_drug_rating(drug_id: int) -> None:
    agg = DrugUserStarRating.objects.filter(drug_id=drug_id).aggregate(a=Avg("stars"))
    avg = agg["a"]
    val = Decimal("0.00") if avg is None else Decimal(str(round(float(avg), 2)))
    Drug.objects.filter(pk=drug_id).update(rating=val)


@receiver(post_save, sender=DrugUserStarRating)
def _on_star_save(sender, instance: DrugUserStarRating, **kwargs) -> None:
    _refresh_drug_rating(instance.drug_id)


@receiver(post_delete, sender=DrugUserStarRating)
def _on_star_del(sender, instance: DrugUserStarRating, **kwargs) -> None:
    _refresh_drug_rating(instance.drug_id)
