import argparse
import base64
import logging
import os
import sys
import warnings
from io import TextIOWrapper
from pathlib import Path
from typing import Dict, Optional

from bridge_plugin import __version__
from bridge_plugin.bridge_config import BridgeConfigLoader
from bridge_plugin.kana_parser import create_kana
from bridge_plugin.model import (
    AudioQuery,
)
from bridge_plugin.part_of_speech_data import MAX_PRIORITY, MIN_PRIORITY
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
    return style_id


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


class App:
    def __init__(
        self,
        text: str,
        synthesis_engines: Dict[str, SynthesisEngineBase],
        latest_core_version: str,
        root_dir: Optional[Path] = None,
        speaker_info_root_dir: Optional[Path] = None,
    ):
        self.text = text
        self.synthesis_engines = synthesis_engines
        self.latest_core_version = latest_core_version
        self.root_dir = root_dir
        self.speaker_info_root_dir = speaker_info_root_dir
        
        if self.root_dir is None:
            self.root_dir = engine_root()
        if self.speaker_info_root_dir is None:
            self.speaker_info_root_dir = engine_root()

        self.default_sampling_rate = self.synthesis_engines[latest_core_version].default_sampling_rate
    
    def get_engine(self, core_version: Optional[str]) -> SynthesisEngineBase:
        if core_version is None:
            return self.synthesis_engines[self.latest_core_version]
        if core_version in self.synthesis_engines:
            return self.synthesis_engines[core_version]
        raise Exception(status_code=422, detail="不明なバージョンです")

    def audio_query(self, style_id):
        """
        クエリの初期値を得ます。ここで得られたクエリはそのまま音声合成に利用できます。各値の意味は`Schemas`を参照してください。
        """
        style_id = get_style_id_from_deprecated(style_id=style_id, speaker_id=self.speaker_info_root_dir)
        engine = self.get_engine(self.latest_core_version)
        accent_phrases = engine.create_accent_phrases(self.text, style_id=style_id)
        return AudioQuery(
            accent_phrases=accent_phrases,
            speedScale=1,
            pitchScale=0,
            intonationScale=1,
            volumeScale=1,
            prePhonemeLength=0.1,
            postPhonemeLength=0.1,
            outputSamplingRate=self.default_sampling_rate,
            outputStereo=False,
            kana=create_kana(accent_phrases),
        )
    


class SpeechSynthesis:
    def __init__(self):
        pass
        
    def audioQueryGenerator(self, text):
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
            "--allow_origin", nargs="*", help="許可するオリジンを指定します。スペースで区切ることで複数指定できます。"
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
        
        app =  App(
                text,
                synthesis_engines,
                latest_core_version,
                root_dir=root_dir,
                speaker_info_root_dir=args.bridge_config_dir,
            )
        return app.audio_query(style_id=1)
        
        
if __name__ == "__main__":
    speechSynthesis = SpeechSynthesis()
    text = "日本語は美しい言語です。"
    print(speechSynthesis.audioQueryGenerator(text))
        
