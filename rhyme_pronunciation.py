"""Bounded, thread-safe local eSpeak NG G2P. No network or audio synthesis.

Language choices are hypotheses, not proof of a name's original pronunciation.
The caller must mark inferred pronunciations and never upgrade them to exact rhymes.
"""
import ctypes
import functools
import re
import threading

_lock=threading.Lock()
_lib=None
_tried=False

def library():
    global _lib,_tried
    if _tried:return _lib
    _tried=True
    try:
        import espeakng_loader
        lib=ctypes.CDLL(espeakng_loader.get_library_path())
        lib.espeak_Initialize.argtypes=[ctypes.c_int,ctypes.c_int,ctypes.c_char_p,ctypes.c_int]
        lib.espeak_Initialize.restype=ctypes.c_int
        lib.espeak_SetVoiceByName.argtypes=[ctypes.c_char_p]
        lib.espeak_SetVoiceByName.restype=ctypes.c_int
        lib.espeak_TextToPhonemes.argtypes=[ctypes.POINTER(ctypes.c_void_p),ctypes.c_int,ctypes.c_int]
        lib.espeak_TextToPhonemes.restype=ctypes.c_char_p
        if lib.espeak_Initialize(2,0,espeakng_loader.get_data_path().encode(),0)>0:_lib=lib
    except (ImportError,OSError,RuntimeError):pass
    return _lib

def available():
    with _lock:return library() is not None

@functools.lru_cache(maxsize=4096)
def phonemize(word,language="de"):
    if not word or len(word)>120 or not any(c.isalpha() for c in word):return ""
    with _lock:
        lib=library()
        if lib is None or lib.espeak_SetVoiceByName(language.encode())!=0:return ""
        buf=ctypes.create_string_buffer(word.encode("utf8")); ptr=ctypes.c_void_p(ctypes.addressof(buf))
        pieces=[]
        for _ in range(12):
            if not ptr.value:break
            result=lib.espeak_TextToPhonemes(ctypes.byref(ptr),1,2)
            if not result:break
            pieces.append(result.decode("utf8",errors="ignore"))
    ipa=re.sub(r"\([^)]*\)","", " ".join(pieces)).strip()
    if language=="de":
        ipa=ipa.replace("ɑ","a").replace("ɾ","ʁ").replace("ɜ","ɐ")
    return ipa

def language_hypotheses(word,english_context=False):
    """Conservative spelling cues for voice selection; never a language verdict."""
    folded=word.casefold()
    if re.search(r"[ñ¿¡]|(?:ez|ález|íguez|illo|illa)$",folded):return ("es","de")
    if re.search(r"[ãõ]|(?:ão|eira|eiro|aldo|iano)$",folded):return ("pt-br","it")
    if re.search(r"(?:ini|oni|etti|ucci|ello|ella|umma|aglia|gli)$",folded):return ("it","de")
    if re.search(r"[éèêçœ]|(?:eau|eaux|ois|ette|eux)$",folded):return ("fr","de")
    if english_context or re.search(r"(?:ham|shire|worth|son|ington|leigh|ough|wood|smith)$",folded):return ("en-us","de")
    return ("de",)
