import re
from dataclasses import dataclass

from videotrans.configure.config import logger, params
from videotrans.translator._openaicompat import OpenAICampat
from videotrans.util import tools

# Model DICH CHUYEN DUNG (dedicated MT): Hunyuan-MT, Qwen-MT, NLLB, Tower...
# Chung khong theo duoc prompt dai co vi du van xuoi: gap mot cau tieng Anh
# trong phan huong dan la chung DICH luon cau do roi nhet vao ket qua. Do la ly
# do co localllm_mt.txt - cung luat khoa dong nhung khong mot cau vi du nao.
# Co lo cho model MT. Lich su cua con so nay, de dung ai hoan nguyen nham:
#  - lo 10 tren cue do silero cat (9/9): chi 1/3 lo dung so dong -> phai ha ve 1
#  - lo 1: 1:1 tuyet doi NHUNG moi cau bi dich trong mu tit -> xung ho nhay loan
#    giua cac cue lien nhau, cau noi do bi hieu thanh cau moi. Mazino nghe ra
#    ngay: "cac cau chua co lien ket voi nhau".
#  - da thu them ngu canh vao prompt (2 cau truoc + 2 cau sau, chi de tham
#    chieu): HONG NANG. Hunyuan nha nguyen khoi tham chieu ra lam ket qua -
#    cue 16 tra ve dung ban dich cua cue 15. Cung kieu hong voi luc no dich ca
#    cau vi du trong prompt. Ket luan: KHONG dua duoc van ban "cam dich" vao
#    prompt cua model MT, moi rao chan bang chu deu vo hieu.
#  - lo 5 tren cue do TEN VAD cat (10/9): 6/6 lo dung so dong, mach cau lien,
#    va NHANH HON lo 1 (0,8 phut vs 1,7 phut). Con so "1/3 lo" cu do tren cue
#    vun cua silero, doi VAD roi thi tien de do khong con dung nua.
CO_LO_MT = 5

MT_MODEL_RE = re.compile(
    r'(hunyuan[-_]?mt|qwen[-_]?mt|nllb|opus[-_]mt|madlad|tower[-_]?instruct|seamless)',
    re.I)


@dataclass
class LocalLLM(OpenAICampat):

    CO_LO_MT = CO_LO_MT

    def __post_init__(self):
        self.ainame ="localllm"
        self.api_key =params.get('localllm_key','')
        self.max_tokens =int(params.get('localllm_max_token')) if params.get(
                'localllm_max_token') else 4096
        self.api_url = params.get('localllm_api','')
        self.model_name = params.get("localllm_model",'')
        super().__post_init__()
        self._chinh_cho_model_mt()

    def _chinh_cho_model_mt(self):
        """Doi sang prompt rieng + co lo rieng, neu ten model bao hieu day la MT.

        Chi ap o che do line-mode (aisendsrt=False): che do srt gui ca file nen
        khong chia lo duoc, va cung khong co ban localllm_mt cho no.

        Vi sao phai tach rieng: model dich chuyen dung manh ve nghia tung cau
        nhung rat yeu ve lam theo chi thi. Prompt chung co cau vi du van xuoi
        thi no DICH luon cau vi du; con so dong thi phai co prompt siet chat
        (localllm_mt) no moi giu duoc. Co lo lay tu CO_LO_MT - xem ghi chu o
        dau file de biet con so do den tu dau, dung sua ma khong do lai.
        """
        if self.aisendsrt or not MT_MODEL_RE.search(self.model_name or ''):
            return
        try:
            self.prompt = tools.get_prompt(
                ainame='localllm_mt', aisendsrt=False
            ).replace('{lang}', self.target_language_name)
        except OSError as e:
            logger.warning(f'[MT] khong doc duoc localllm_mt.txt, dung prompt chung: {e}')
            return
        self.trans_thread = self.CO_LO_MT
        logger.info(f'[MT] model dich `{self.model_name}`: dung prompt localllm_mt, '
                    f'co lo = {self.CO_LO_MT} dong')
