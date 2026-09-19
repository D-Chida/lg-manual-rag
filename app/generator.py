from abc import ABC, abstractmethod
from typing import Any, Dict, List


class BaseGenerator(ABC):
    """
    回答生成エンジンの基底抽象クラス（Strategyパターン）。
    将来的な外部LLM（OpenAI, Azure OpenAI, Gemini等）やローカルLLMへの切り替えに対応する。
    """

    @abstractmethod
    def generate_answer(
        self, query: str, retrieved_docs: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        質問と検索されたマニュアルチャンクを受け取り、4分割の構造化回答辞書を生成して返却する。
        """
        pass


class LocalRuleBasedGenerator(BaseGenerator):
    """
    外部API通信を行わず、検索されたマニュアル本文およびメタデータから
    結論・市民向け説明・職員操作手順・参照情報を抽出・構成するローカル生成エンジン。
    """

    # マニュアル未収録業務（未納・未払い・滞納・督促など）の判定用キーワード
    UNSUPPORTED_KEYWORDS = [
        "未納",
        "未払い",
        "未はらい",
        "滞納",
        "督促",
        "催促",
        "催告",
        "延滞",
        "分割納付",
        "給水停止",
        "支払猶予",
        "払えない",
        "納期限",
        "未済",
    ]

    # 本マニュアルが対象とする業務ドメインの判定キーワード
    SUPPORTED_DOMAIN_KEYWORDS = [
        # 01_漏水減免・更正
        "漏水",
        "減免",
        "更正",
        "水漏れ",
        "地下",
        "埋設",
        "配管",
        "蛇口",
        "トイレ",
        "器具",
        "修繕",
        "k-12",
        # 02_異動・開閉栓
        "開栓",
        "閉栓",
        "名義",
        "承継",
        "手数料",
        "水栓",
        "wtr-001",
        "使用開始",
        "使用中止",
        # 03_検針異常・メーター管理
        "検針",
        "メーター",
        "指示数",
        "急増",
        "急減",
        "異常",
        "アラート",
        "調査票",
        "e-402",
        "wtr-mtr-205",
    ]

    def generate_answer(
        self, query: str, retrieved_docs: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        q = query.lower()

        # ----------------------------------------------------
        # 安全装置（フォールバック処理）: 未収録業務・低適合度の判定
        # ----------------------------------------------------
        is_unsupported = any(k in q for k in self.UNSUPPORTED_KEYWORDS)

        # 例外: 名義変更・承継における「前使用者の未納分承継可否」はマニュアル記載範囲のため許容
        if is_unsupported and any(w in q for w in ["名義", "承継", "前使用者", "新使用者"]):
            is_unsupported = False

        # ドメイン適合度判定: 収録業務キーワードが含まれているか
        has_supported_keyword = any(k in q for k in self.SUPPORTED_DOMAIN_KEYWORDS)

        # ドキュメントが空、未収録業務、または適合度が低い場合はフォールバック
        if not retrieved_docs or is_unsupported or not has_supported_keyword:
            return {
                "conclusion": "該当する業務マニュアルが確認できませんでした。自己判断せず有識者（料金担当係）に確認してください。",
                "explanation_for_citizen": "水道料金の未払い・納期限経過後の対応については、本マニュアルの対象外となります。恐れ入りますが、料金係窓口または担当者へお問い合わせいただけますようご案内ください。",
                "staff_action": (
                    "【職員対応手順】\n"
                    "1. 独断での減免・免除案内は厳禁です。\n"
                    "2. 基幹システム「収納管理」画面にて未納月数および督促履歴を確認。\n"
                    "3. 収納担当の有識者・主任へ事案を引き継ぎ、指示を仰いでください。"
                ),
                "references": [],
            }

        # ----------------------------------------------------
        # 通常処理: 参照情報の抽出（重複排除）
        # ----------------------------------------------------
        references: List[Dict[str, str]] = []
        seen_refs = set()
        for doc in retrieved_docs:
            meta = doc.get("metadata", {})
            src = meta.get("source", "")
            sec = meta.get("section", "")
            if (src, sec) not in seen_refs and (src or sec):
                seen_refs.add((src, sec))
                references.append({"source": src, "section": sec})

        combined_contents = "\n\n".join(doc.get("content", "") for doc in retrieved_docs)
        sources = [doc.get("metadata", {}).get("source", "") for doc in retrieved_docs]
        sections = [doc.get("metadata", {}).get("section", "") for doc in retrieved_docs]

        # 1. 結論 (conclusion)
        conclusion = ""
        # 漏水減免関連
        if any(w in q for w in ["トイレ", "蛇口", "閉め忘れ", "露出", "器具", "給湯器"]):
            conclusion = "減免の対象外です。給水器具（蛇口、水洗トイレ、給湯器等）の不具合や露出配管の破損、閉め忘れによる漏水は減免対象外となり、全額利用者負担となります。"
        elif any(w in q for w in ["地下", "埋設", "不可抗力", "壁体", "床下"]):
            conclusion = "減免対象となります。地下埋設管や壁体内配管など、通常発見困難な不可抗力による漏水は、指定給水装置工事事業者による修繕完了を条件に減免（原則50%減額）の適用対象です。"
        elif any(w in q for w in ["漏水", "減免", "更正", "k-12"]):
            conclusion = "不可抗力による地下漏水等に限り減免（原則50%減額）が適用されます。露出配管や給水器具（蛇口・トイレ等）の故障・閉め忘れは対象外です。"
        # 開閉栓・名義変更関連
        elif any(w in q for w in ["開栓", "閉栓", "開始", "中止", "期日", "日数"]):
            conclusion = "使用開始（開栓）・使用中止（閉栓）の受付は、希望日の「3営業日前」までが原則です（当日緊急開栓は例外扱いとなります）。"
        elif any(w in q for w in ["名義", "変更", "承継", "死亡", "相続"]):
            conclusion = "相続等による承継の場合は従前の権利義務を引き継ぎますが、賃貸退去・売買等による新旧交代は前使用者の閉栓と新使用者の新規開栓手続きが必要です。前使用者の未納分を新使用者へ請求することはできません。"
        elif any(w in q for w in ["手数料", "費用", "いくら"]):
            conclusion = "開栓事務手数料は1件につき1,000円（非課税）です（初回検針時に合算請求。生活保護世帯等に対する免除規定あり）。"
        # 検針異常・メーター関連
        elif any(w in q for w in ["200%", "急増", "急減", "異常", "アラート"]):
            conclusion = "当期使用水量が前年同期比200%以上（かつ差分30m³以上）の場合、水量急増アラートが発生し調定確定が自動保留されます。2営業日以内の現地調査が必要です。"
        elif any(w in q for w in ["e-402", "精査", "エラー"]):
            conclusion = "エラーコード「E-402（水量急増・漏水疑い）」は、現場調査票の調査結果に基づき精査完了（調定承認）または再検針指示を行って解除します。"
        else:
            first_sec = sections[0] if sections else "マニュアル規定"
            conclusion = f"マニュアル規定（{first_sec}）に準拠した所定の手続き・判定を行ってください。"

        # 2. 市民への納得感ある説明材料 (explanation_for_citizen)
        explanation = ""
        if any("01_漏水減免" in s for s in sources) or any(w in combined_contents for w in ["減免", "漏水", "算定式"]):
            explanation = (
                "【市民への案内要点】\n"
                "・地下埋設管など、お客様が日常管理で発見することが困難な不可抗力の漏水に限り、水道料金の減額更正（原則50%減免）を行う制度です。\n"
                "・蛇口の閉め忘れや水洗トイレのロータンク・ボールタップ故障、給湯器からの水漏れは発見可能な器具の破損にあたるため、条例上減免対象外となります。\n"
                "・減免申請には、市が指定した「指定給水装置工事事業者」による修繕完了証明書（写真添付）と減免申請書の提出が必要です。\n"
                "・減免水量算定式：当期検針水量から前年同期実績（基準水量）を引いた漏水推定水量の50%を減免します（下水道に流れていない地下漏水は下水道使用料100%減免）。"
            )
        elif any("02_異動" in s for s in sources) or any(w in combined_contents for w in ["開栓", "閉栓", "名義変更", "水栓"]):
            explanation = (
                "【市民への案内要点】\n"
                "・お引越し等に伴う水道の開栓・閉栓は、作業希望日の3営業日前までにお手続きいただくようお願いいたします。\n"
                "・開栓事務手数料として1件1,000円を申し受け、初回検針時の水道料金に合算してご請求いたします（生活保護世帯等は申請により免除）。\n"
                "・前入居者様の未納水道料金がある場合でも、新しい入居者様へ請求が引き継がれることは一切ございません。"
            )
        elif any("03_検針異常" in s for s in sources) or any(w in combined_contents for w in ["検針", "急増", "調査票", "メーター"]):
            explanation = (
                "【市民への案内要点】\n"
                "・前年同時期と比較して使用水量が大幅に増加（200%以上）しているため、請求を一時保留にし、検針誤読や地下漏水がないか調査を実施しております。\n"
                "・指示票発行後2営業日以内に調査員が現地へ赴き、水道メーターのパイロットマーク回転（漏水有無）や指針確認を行いますので、調査結果をお待ちください。"
            )
        else:
            paras = [p.strip() for p in combined_contents.split("\n") if len(p.strip()) > 20 and not p.strip().startswith("第")]
            explanation = "\n".join(paras[:3]) if paras else combined_contents[:200]

        # 3. 職員が端末等で取るべき操作フロー (staff_action)
        staff_action = ""
        if "料金更正管理" in combined_contents or "K-12" in combined_contents or any("01_漏水減免" in s for s in sources):
            staff_action = (
                "【端末操作フロー】\n"
                "1. 上下水道基幹システム「業務処理」→「収納・更正業務」→「料金更正管理」を選択。\n"
                "2. お客様の水栓番号または調定番号を入力し、対象調定レコードを検索。\n"
                "3. 処理区分「減額更正」を選択し、更正事由コード欄に「K-12」（給水管地下漏水に伴う減免更正）を入力。\n"
                "4. 「算定水量算出」を押下して前年同期実績との差分および減免率50%の再計算結果を確認。\n"
                "5. 様式第4号「減免申請書」と工事業者の「修繕完了証明書」のスキャンデータを添付し、電子決裁（課長承認）へ回付。"
            )
        elif "WTR-001" in combined_contents or "水栓管理" in combined_contents or any("02_異動" in s for s in sources):
            staff_action = (
                "【端末操作フロー】\n"
                "1. 基幹ポータル画面から「水栓管理」（画面ID: WTR-001）を起動。\n"
                "2. 10桁の水栓番号で照会し、「異動処理」タブを展開。\n"
                "3. 異動フラグ（開栓時「1」、閉栓時「2」）を選択し、異動希望日および使用者情報を登録。\n"
                "4. 即時反映が必要な場合は画面上の「ハンディ緊急即時送信」を押下（通常は17:00 / 翌朝08:30に自動バッチ連携）。\n"
                "5. 通信ステータスが「HND-OK-01（正常連携完了）」となったことを確認。"
            )
        elif "WTR-MTR-205" in combined_contents or "E-402" in combined_contents or any("03_検針異常" in s for s in sources):
            staff_action = (
                "【端末操作フロー】\n"
                "1. システムメニュー「検針管理業務」→「検針データ精査」（画面ID: WTR-MTR-205）を起動。\n"
                "2. 検針区および年月を指定し、エラーコード「E-402（水量急増・漏水疑い）」の該当データを抽出。\n"
                "3. 現場調査票（2営業日以内現地確認）の受付番号と精査事由区分（01:家族増、02:散水工事、03:漏水認定等）を入力。\n"
                "4. 正常使用または漏水減免移行の場合は「エラー解除フラグ」にチェックを入れ「精査完了（調定承認）」を押下。\n"
                "5. 誤検針・メーター故障疑いの場合は「再検針指示」ボタンよりハンディ端末へ再調査指示を配信。"
            )
        else:
            staff_action = "該当マニュアルの端末操作手順章を参照し、所定の業務画面から入力・決裁を行ってください。"

        return {
            "conclusion": conclusion,
            "explanation_for_citizen": explanation,
            "staff_action": staff_action,
            "references": references,
        }


def get_generator() -> BaseGenerator:
    """
    回答生成エンジンのファクトリ関数。
    現在は LocalRuleBasedGenerator を返却する。将来の外部LLM連携時の切り替え口となる。
    """
    return LocalRuleBasedGenerator()
