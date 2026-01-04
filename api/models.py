# api/models.py
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, field_validator

class ChartOptions(BaseModel):
    sort: Optional[bool] = True
    stacked: Optional[bool] = False
    orientation: Optional[str] = "vertical"
    legend: Optional[bool] = True
    group_by: Optional[Union[str, None]] = None
    filter_description: Optional[str] = None
    # cosmetics/UX
    rolling: Optional[int] = None
    top_n: Optional[int] = None
    x_rotate: Optional[int] = 0
    y_fmt: Optional[str] = None      # "int"|"float0"|"float1"|"k"
    theme: Optional[str] = "light"   # "light"|"dark"

class ChartSpec(BaseModel):
    type: str = Field(pattern="^(bar|line|area|pie|scatter)$")
    x: Optional[str] = None
    y: Union[str, List[str], None] = None
    series: Optional[str] = None
    title: Optional[str] = None
    x_label: Optional[str] = None
    y_label: Optional[str] = None
    options: Optional[ChartOptions] = ChartOptions()

    @field_validator("type")
    @classmethod
    def _validate_type(cls, v: str) -> str:
        allowed = {"bar", "line", "area", "pie", "scatter"}
        if v not in allowed:
            raise ValueError(f"type doit être dans {allowed}")
        return v

class RequestSpec(BaseModel):
    sql: str
    params: Optional[Dict[str, Any]] = None
    chart: ChartSpec
    schema: Optional[str] = None  # permet de cibler un schéma (ligue) pour le search_path
