import argparse
import base64
import logging
import os
import re
import sys
import warnings
from io import TextIOWrapper
from pathlib import Path
from typing import Dict, List, Optional
import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse

from bridge_plugin import __version__
from bridge_plugin.bridge_config import BridgeConfigLoader
from bridge_plugin.kana_parser import create_kana
from bridge_plugin.model import (
    AudioQuery,
    BaseLibraryInfo,
    VvlibManifest,
)
from bridge_plugin.part_of_speech_data import MAX_PRIORITY, MIN_PRIORITY
from bridge_plugin.setting import (
    USER_SETTING_PATH,
    CorsPolicyMode,
    SettingLoader,
)
from bridge_plugin.synthesis_engine import SynthesisEngineBase, make_synthesis_engines

from bridge_plugin.utility import (
    engine_root,
    get_latest_core_version,
)

logging.getLogger("uvicorn").propagate = False


def get_style_id_from_deprecated(style_id: int | None, speaker_id: int | None) -> int:
    if speaker_id is not None and style_id is None:
        warnings.warn("speakerは非推奨です。style_idを利用してください。", stacklevel=1)
        return speaker_id
    elif style_id is not None and speaker_id is None:
        return style_id
    raise HTTPException(
        status_code=400, detail="speakerとstyle_idが両方とも存在しないか、両方とも存在しています。"
    )


def b64encode_str(s):
    return base64.b64encode(s).decode("utf-8")


def set_output_log_utf8() -> None:
    if sys.stdout is not None:
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except AttributeError:
            sys.stdout.flush()
            sys.stdout = TextIOWrapper(
                sys.stdout.buffer, encoding="utf-8", errors="backslashreplace"
            )
    if sys.stderr is not None:
        try:
            sys.stderr.reconfigure(encoding="utf-8")
        except AttributeError:
            sys.stderr.flush()
            sys.stderr = TextIOWrapper(
                sys.stderr.buffer, encoding="utf-8", errors="backslashreplace"
            )


def generate_app(
    text: str,
    synthesis_engines: Dict[str, SynthesisEngineBase],
    latest_core_version: str,
    root_dir: Optional[Path] = None,
    speaker_info_root_dir: Optional[Path] = None,
) -> AudioQuery:
    if root_dir is None:
        root_dir = engine_root()
    if speaker_info_root_dir is None:
        speaker_info_root_dir = engine_root()

    default_sampling_rate = synthesis_engines[latest_core_version].default_sampling_rate

    # app = FastAPI(
    #     title="Bridge Plugin",
    #     description="VOICEVOX互換の音声合成エンジンです。",
    #     version=__version__,
    # )

    # CORS用のヘッダを生成するミドルウェア
    # localhost_regex = "^https?://(localhost|127\\.0\\.0\\.1)(:[0-9]+)?$"
    # compiled_localhost_regex = re.compile(localhost_regex)
    # allowed_origins = ["*"]
    # if cors_policy_mode == "localapps":
    #     allowed_origins = ["app://."]
    #     if allow_origin is not None:
    #         allowed_origins += allow_origin
    #         if "*" in allow_origin:
    #             print(
    #                 'WARNING: Deprecated use of argument "*" in allow_origin. '
    #                 'Use option "--cors_policy_mod all" instead. See "--help" for more.',
    #                 file=sys.stderr,
    #             )

    # app.add_middleware(
    #     CORSMiddleware,
    #     allow_origins=allowed_origins,
    #     allow_credentials=True,
    #     allow_origin_regex=localhost_regex,
    #     allow_methods=["*"],
    #     allow_headers=["*"],
    # )

    # @app.middleware("http")
    # async def block_origin_middleware(request: Request, call_next):
    #     isValidOrigin: bool = False
    #     if "Origin" not in request.headers:  # Originのない純粋なリクエストの場合
    #         isValidOrigin = True
    #     elif "*" in allowed_origins:  # すべてを許可する設定の場合
    #         isValidOrigin = True
    #     elif request.headers["Origin"] in allowed_origins:  # Originが許可されている場合
    #         isValidOrigin = True
    #     elif compiled_localhost_regex.fullmatch(
    #         request.headers["Origin"]
    #     ):  # localhostの場合
    #         isValidOrigin = True

    #     if isValidOrigin:
    #         return await call_next(request)
    #     else:
    #         return JSONResponse(
    #             status_code=403, content={"detail": "Origin not allowed"}
    #         )

    def get_engine(core_version: Optional[str]) -> SynthesisEngineBase:
        if core_version is None:
            return synthesis_engines[latest_core_version]
        if core_version in synthesis_engines:
            return synthesis_engines[core_version]
        raise HTTPException(status_code=422, detail="不明なバージョンです")

    # @app.post(
    #     "/audio_query",
    #     response_model=AudioQuery,
    #     tags=["クエリ作成"],
    #     summary="音声合成用のクエリを作成する",
    # )
    def audio_query(
        text: str = text,
        style_id: int | None = Query(default=None),  # noqa: B008
        speaker: int | None = Query(default=None, deprecated=True),  # noqa: B008
        core_version: str | None = None,
    ) -> AudioQuery:
        """
        クエリの初期値を得ます。ここで得られたクエリはそのまま音声合成に利用できます。各値の意味は`Schemas`を参照してください。
        """
        style_id = get_style_id_from_deprecated(style_id=style_id, speaker_id=speaker)
        engine = get_engine(core_version)
        accent_phrases = engine.create_accent_phrases(text, style_id=style_id)
        return AudioQuery(
            accent_phrases=accent_phrases,
            speedScale=1,
            pitchScale=0,
            intonationScale=1,
            volumeScale=1,
            prePhonemeLength=0.1,
            postPhonemeLength=0.1,
            outputSamplingRate=default_sampling_rate,
            outputStereo=False,
            kana=create_kana(accent_phrases),
        )
        
    # def custom_openapi():
    #     if app.openapi_schema:
    #         return app.openapi_schema
    #     openapi_schema = get_openapi(
    #         title=app.title,
    #         version=app.version,
    #         description=app.description,
    #         routes=app.routes,
    #         tags=app.openapi_tags,
    #         servers=app.servers,
    #         terms_of_service=app.terms_of_service,
    #         contact=app.contact,
    #         license_info=app.license_info,
    #     )
    #     openapi_schema["components"]["schemas"][
    #         "VvlibManifest"
    #     ] = VvlibManifest.schema()
    #     base_library_info = BaseLibraryInfo.schema(
    #         ref_template="#/components/schemas/{model}"
    #     )
    #     del base_library_info["definitions"]
    #     openapi_schema["components"]["schemas"]["BaseLibraryInfo"] = base_library_info
    #     app.openapi_schema = openapi_schema
    #     return openapi_schema

    # app.openapi = custom_openapi

    return audio_query


def main() -> None:

    output_log_utf8 = os.getenv("VV_OUTPUT_LOG_UTF8", default="")
    if output_log_utf8 == "1":
        set_output_log_utf8()
    elif not (output_log_utf8 == "" or output_log_utf8 == "0"):
        print(
            "WARNING:  invalid VV_OUTPUT_LOG_UTF8 environment variable value",
            file=sys.stderr,
        )

    parser = argparse.ArgumentParser(description="VOICEVOX のエンジンです。")
    parser.add_argument("--host", type=str, default=None, help="接続を受け付けるホストアドレスです。")
    parser.add_argument("--port", type=int, default=None, help="接続を受け付けるポート番号です。")
    parser.add_argument(
        "--use_gpu", action="store_true", help="指定するとGPUを使って音声合成するようになります。"
    )
    parser.add_argument(
        "--voicevox_dir",
        type=Path,
        default=None,
        help="この引数は無視されます。（VOICEVOX Engineとの互換性のために維持されています。）",
    )
    parser.add_argument(
        "--voicelib_dir",
        type=Path,
        default=None,
        action="append",
        help="この引数は無視されます。（VOICEVOX Engineとの互換性のために維持されています。）",
    )
    parser.add_argument(
        "--runtime_dir",
        type=Path,
        default=None,
        action="append",
        help="この引数は無視されます。（VOICEVOX Engineとの互換性のために維持されています。）",
    )
    parser.add_argument(
        "--enable_mock",
        action="store_true",
        help="指定するとVOICEVOX COREを使わずモックで音声合成を行います。",
    )
    parser.add_argument(
        "--enable_cancellable_synthesis",
        action="store_true",
        help="この引数は無視されます。（VOICEVOX Engineとの互換性のために維持されています。）",
    )
    parser.add_argument(
        "--init_processes",
        type=int,
        default=2,
        help="cancellable_synthesis機能の初期化時に生成するプロセス数です。",
    )
    parser.add_argument(
        "--load_all_models", action="store_true", help="指定すると起動時に全ての音声合成モデルを読み込みます。"
    )

    parser.add_argument(
        "--cpu_num_threads",
        type=int,
        default=None,
        help="この引数は無視されます。（VOICEVOX Engineとの互換性のために維持されています。）",
    )

    parser.add_argument(
        "--output_log_utf8",
        action="store_true",
        help=(
            "指定するとログ出力をUTF-8でおこないます。指定しないと、代わりに環境変数 VV_OUTPUT_LOG_UTF8 の値が使われます。"
            "VV_OUTPUT_LOG_UTF8 の値が1の場合はUTF-8で、0または空文字、値がない場合は環境によって自動的に決定されます。"
        ),
    )

    parser.add_argument(
        "--cors_policy_mode",
        type=CorsPolicyMode,
        choices=list(CorsPolicyMode),
        default=None,
        help=(
            "CORSの許可モード。allまたはlocalappsが指定できます。allはすべてを許可します。"
            "localappsはオリジン間リソース共有ポリシーを、app://.とlocalhost関連に限定します。"
            "その他のオリジンはallow_originオプションで追加できます。デフォルトはlocalapps。"
        ),
    )

    parser.add_argument(
        "--allow_origin", nargs="*", help="許可するオリジンを指定します。スペースで区切ることで複数指定できます。"
    )

    parser.add_argument(
        "--setting_file", type=Path, default=USER_SETTING_PATH, help="設定ファイルを指定できます。"
    )

    parser.add_argument(
        "--bridge_config_dir",
        type=Path,
        default=engine_root(),
        help="Bridge Configファイルのあるディレクトリです。",
    )

    parser.add_argument(
        "--preset_file",
        type=Path,
        default=None,
        help=(
            "プリセットファイルを指定できます。"
            "指定がない場合、環境変数 VV_PRESET_FILE、--voicevox_dirのpresets.yaml、"
            "実行ファイルのディレクトリのpresets.yamlを順に探します。"
        ),
    )

    args = parser.parse_args()

    bridge_config_loader = BridgeConfigLoader(args.bridge_config_dir)

    if args.output_log_utf8:
        set_output_log_utf8()

    # Synthesis Engine
    use_gpu: bool = args.use_gpu
    enable_mock: bool = args.enable_mock
    load_all_models: bool = args.load_all_models

    synthesis_engines = make_synthesis_engines(
        use_gpu=use_gpu,
        enable_mock=enable_mock,
        load_all_models=load_all_models,
        bridge_config_loader=bridge_config_loader,
    )
    assert len(synthesis_engines) != 0, "音声合成エンジンがありません。"
    latest_core_version = get_latest_core_version(versions=synthesis_engines.keys())

    root_dir: Path | None = None
    if root_dir is None:
        root_dir = engine_root()

    setting_loader = SettingLoader(args.setting_file)

    settings = setting_loader.load_setting_file()

    cors_policy_mode: CorsPolicyMode | None = args.cors_policy_mode
    if cors_policy_mode is None:
        cors_policy_mode = settings.cors_policy_mode

    # allow_origin = None
    # if args.allow_origin is not None:
    #     allow_origin = args.allow_origin
    # elif settings.allow_origin is not None:
    #     allow_origin = settings.allow_origin.split(" ")

    # bridge_config = bridge_config_loader.load_config_file()
    # host = bridge_config.host if args.host is None else args.host
    # port = bridge_config.port if args.port is None else args.port
    
    text = "日本語は美しい言語です。"
    
    return generate_app(
            text,
            synthesis_engines,
            latest_core_version,
            root_dir=root_dir,
            speaker_info_root_dir=args.bridge_config_dir,
        )
    
if __name__ == "__main__":
    print(main())
