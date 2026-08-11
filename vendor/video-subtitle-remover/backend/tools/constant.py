from enum import Enum, unique

@unique
class InpaintMode(Enum):
    """
    图像重绘算法枚举
    """
    STTN_AUTO = "sttn-auto"
    STTN_DET = "sttn-det"
    LAMA = "lama"
    PROPAINTER = "propainter"
    OPENCV = "opencv"
    # 2 mode tuy chinh cho pipeline nay: ap THANG vao vung nguoi dung khoanh
    # (self.sub_areas), KHONG chay OCR detect (giong sttn-auto) - dung cho
    # logo/sub CO DINH suot video ma STTN khong xoa duoc (STTN muon frame khac
    # de tham chieu, logo co dinh thi frame nao cung co -> tai tao lai y nguyen).
    LAMA_AUTO = "lama-auto"   # inpaint AI tung frame doc lap (xoa han, co the nhoe)
    BLUR = "blur"             # lam mo vung (che, dang tin cay, khong can model)

@unique
class SubtitleDetectMode(Enum):
    """
    字幕检测算法枚举
    """
    PP_OCRv5_MOBILE = "PP_OCRv5_MOBILE"
    PP_OCRv5_SERVER = "PP_OCRv5_SERVER"