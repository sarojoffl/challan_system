from django import template
from challan.nepali_date import ad_to_bs_display

register = template.Library()


@register.filter(name="bs_date")
def bs_date(value):
    """Convert AD date/datetime to BS display string.  e.g. 'Bhadra 10, 2083'"""
    return ad_to_bs_display(value)


@register.filter(name="bs_date_only")
def bs_date_only(value):
    """Same as bs_date but without year – e.g. 'Bhadra 10'"""
    return ad_to_bs_display(value, include_year=False)
