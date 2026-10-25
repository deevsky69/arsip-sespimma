from django import template

from arsip.models import tingkat_kemiripan

register = template.Library()


@register.inclusion_tag("arsip/_label_kemiripan.html")
def label_kemiripan(persen):
    kode, label = tingkat_kemiripan(persen or 0)
    return {"persen": persen or 0, "kode": kode, "label": label}
