import pandas as pd
import numpy as np
from pathlib import Path
from PIL import Image
from PIL.ExifTags import Base,GPS,IFD,TAGS,GPSTAGS 
from tqdm import tqdm

use_tag_ids = {
    "0th IFD":[
        Base.DateTime,
        Base.Model,
        Base.Software,
        Base.Orientation
    ],
    "Exif IFD":[
        Base.DateTimeOriginal,
        Base.DateTimeDigitized,
        Base.SubsecTime,
        Base.SubsecTimeOriginal,
        Base.SubsecTimeDigitized,
        Base.FNumber,
        Base.ExposureTime,
        Base.ISOSpeedRatings,
        Base.FocalLength,
        Base.FocalLengthIn35mmFilm,
        Base.ExposureProgram,
        Base.SceneCaptureType,
        Base.LensModel
    ],
    "GPS Info IFD":[
        GPS.GPSLatitude,
        GPS.GPSLatitudeRef,
        GPS.GPSLongitude,
        GPS.GPSLongitudeRef
    ]
}

MODE_DICT = {
    "ExposureProgram":{
        0:"未定義",
        1:"マニュアル",
        2:"ノーマルプログラム",
        3:"絞り優先",
        4:"シャッター優先",
        5:"creativeプログラム",  # 被写界深度方向にバイアス
        6:"actionプログラム",  # シャッタースピード高速側にバイアス
        7:"ポートレイトモード",  # クローズアップ撮影、背景フォーカス外す
        8:"ランドスケープモード",  # landscape撮影、背景はフォーカス合う
    },
    "SceneCaptureType":{
        0:"標準",
        1:"風景",
        2:"人物",
        3:"夜景"
    }
}

def load_exif(path):
    with Image.open(path) as im:
        exif = im.getexif()
    # 各IFDの情報を必要なタグだけ取得
    zeroth_ifd = {TAGS[tag_id]: value for tag_id, value in exif.items() 
                        if tag_id in use_tag_ids["0th IFD"]} 
    exif_ifd = {TAGS[tag_id]: value for tag_id, value in exif.get_ifd(IFD.Exif).items() 
                        if tag_id in use_tag_ids["Exif IFD"]} 
    gps_ifd = {GPSTAGS[tag_id]: value for tag_id, value in exif.get_ifd(IFD.GPSInfo).items()
                        if tag_id in use_tag_ids["GPS Info IFD"]} 
    exif_dict = dict(**zeroth_ifd,**exif_ifd,**gps_ifd) # 辞書の連結
    exif_dict["path"] = path
    
    return exif_dict

def convert_exif_cols(exif_df):
    # datetime型への変換
    time_subsec = [("DateTime",         "SubsecTime"),  # 日付系のカラム名と対応するSubsec(ミリ秒情報)のカラム名
                    ("DateTimeOriginal", "SubsecTimeOriginal"),
                    ("DateTimeDigitized","SubsecTimeDigitized")]
    for time,subsec in time_subsec:
        if subsec in exif_df.columns: # ミリ秒情報があれば日付情報にマージしdatetime化
            exif_df[time] = exif_df[time].astype(str).replace("nan","")+"."\
                            +exif_df[subsec].astype(str).replace("nan","0")# 日付と小数点以下を"."で連結
            exif_df[time] = exif_df[time].replace(".0",np.nan) # 日付自体が欠損の場合↑の処理によって".0"だけになるので欠損にする
            exif_df[time] = pd.to_datetime(exif_df[time],format='%Y:%m:%d %H:%M:%S.%f',errors='coerce')
        elif time in exif_df.columns: # なければそのままdatetime化
            exif_df[time] = pd.to_datetime(exif_df[time],format='%Y:%m:%d %H:%M:%S')

    exif_df["FocalLength"] = exif_df["FocalLength"].astype(float)
    exif_df["FNumber"] = exif_df["FNumber"].astype(float)
    exif_df["ShutterSpeed"] = exif_df["ExposureTime"].map(lambda x:str(x.real)) # 分数表記
    exif_df["ExposureTime"] = exif_df["ExposureTime"].astype(float) # 数値

    # カテゴリ情報をカラムに関して、番号をカテゴリ名に変換
    for key in MODE_DICT.keys():
        if(key in exif_df.columns):
            exif_df[key] = exif_df[key].map(MODE_DICT[key])

    # GPS情報の変換（度分秒のタプル→度）
    exif_df["GPSLatitude"]  = exif_df["GPSLatitude"].map(dms2deg).astype(float)
    exif_df["GPSLongitude"] = exif_df["GPSLongitude"].map(dms2deg).astype(float)
    exif_df["GPSLatitude"]  =  exif_df["GPSLatitude"]*exif_df["GPSLatitudeRef"].replace("N",1).replace("S",-1)
    exif_df["GPSLongitude"] =  exif_df["GPSLongitude"]*exif_df["GPSLongitudeRef"].replace("E",1).replace("W",-1)

    # 欠損の場合0が入るみたいなので改めて欠損に置換
    int_cols = ["FocalLength","FocalLengthIn35mmFilm"]
    exif_df[int_cols] = exif_df[int_cols].replace(0,pd.NA)
    float_cols = ["FNumber","ExposureTime","GPSLatitude","GPSLongitude"]
    exif_df[float_cols] = exif_df[float_cols].replace(0,np.nan)

    return exif_df

# GPSデータの処理に使用
def dms2deg(x):
    # 緯度経度の度分秒フォーマットを度に変換
    return x[0]+x[1]/60+x[2]/3600 if type(x)==tuple else np.nan

def categorize_focal_length(x):
    # 参考
    # https://ptl.imagegateway.net/contents/original/glossary/標準レンズ、広角レンズ、望遠レンズ.html
    # https://av.jpn.support.panasonic.com/support/dsc/knowhow/knowhow21.html
    # https://goopass.jp/magazine/300mmsupertelephotoens10/
    if(pd.isna(x)):
        return np.nan
    elif(x<24):
        return "超広角(～23mm)"
    elif(x<35):
        return "広角(24～34mm)"
    elif(x<100):
        return "標準(35～99mm)"
    elif(x<300):
        return "望遠(100～299mm)"
    elif(x>=300):
        return "超望遠(300～mm)"
    
def categorize_exposure_time(x):
    if(pd.isna(x)):
        return np.nan
    elif(x<=1/1000):
        return "～1/1000sec"
    elif(x<1):
        return "1/800～1/10sec"
    elif(x>=1):
        return "1/8～sec"
    
def categorize_f_number(x):
    # 参考
    # https://photobook.ikuji-park.com/f-number.html
    if(pd.isna(x)):
        return np.nan
    elif(x<4):
        return "～F3.5"
    elif(x<8):
        return "F4～F7.1"
    elif(x<13):
        return "F8～F11"
    elif(x>=13):
        return "F13～"

def add_extra_cols(exif_df):
    exif_df["FocalLengthCategory"] = exif_df["FocalLengthIn35mmFilm"].map(categorize_focal_length)
    exif_df["ExposureTimeCategory"] = exif_df["ExposureTime"].map(categorize_exposure_time)
    exif_df["FNumberCategory"] = exif_df["FNumber"].map(categorize_f_number)
    return exif_df

def get_exif_df(path_list):
    exif_dict_list = [load_exif(path) for path in tqdm(path_list)]
    exif_df = pd.DataFrame(exif_dict_list)
    exif_df = convert_exif_cols(exif_df) # 型変換
    exif_df = add_extra_cols(exif_df) # カテゴリカラム追加
    return exif_df

# 既存のexif_dfがあれば、path_listからはまだ存在しないpathだけ読み込んで追加する
def get_exif_df_add(path_list,existing_exif_df=None):
    additional_path_list = sorted(set(path_list)-set(existing_exif_df["path"]))
    additional_exif_df = get_exif_df(additional_path_list)
    exif_df = pd.concat([existing_exif_df,additional_exif_df],ignore_index=True)
    return exif_df
