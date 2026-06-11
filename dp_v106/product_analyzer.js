// v21.8.24.13 상품 자동 분석 라우터 - 자동화 패키지 우선 분류/쿠팡 잡정보 제거
// 사용자가 카테고리를 고르지 않아도 상품명/링크/고급입력/원본 이미지 첨부 상태를 바탕으로 템플릿을 고릅니다.
(function(){
  const RULES = [
    {
      key:'shoe_care', category_group:'신발관리/가죽관리', template_type:'care_before_after',
      patterns:[/구두약|구두 광택|슈케어|신발관리|신발 관리|신발클리너|가죽크림|가죽 관리|방수스프레이|shoe polish|shoe care|leather/i],
      product_type:'관리/케어 상품',
      target_customer:'구두나 가죽 제품을 깔끔하게 관리하고 싶은 직장인, 외출 전 신발 상태를 신경 쓰는 사용자',
      main_pain_point:'검정 구두나 가죽 제품이 쉽게 칙칙해지고 관리가 번거롭게 느껴짐',
      core_value:'간편한 흑색 케어, 작은 용기, 보관 부담이 적은 신발관리',
      spec_hint:'용량, 색상, 사용 가능 소재, 사용 방법, 주의사항 확인 필요',
      competitor_hint:'일반 신발관리용품은 사용법/색상/관리 대상 설명이 부족할 수 있음',
      sections:['HERO','PROBLEM','HOW_TO_USE','DETAIL','BEFORE_AFTER','STORAGE','FAQ','CTA']
    },
    {
      // v21.8.24.68: 신발(footwear) 전용 신설 — '운동화·스니커즈·구두' 등은 기존 신발'관리'(shoe_care)와 달라
      //  착용/핏/사이즈 중심 구조가 필요. 모델·종류 명칭이 카테고리 단어를 안 가져 general로 빠지던 문제 해결.
      key:'footwear', category_group:'신발/슈즈', template_type:'wear_fit',
      patterns:[/운동화|스니커즈|구두|샌들|부츠|슬리퍼|로퍼|런닝화|러닝화|워킹화|워커|어그|뮬|플랫슈즈|단화|모카신|첼시부츠|레인부츠|크록스|쪼리|조리|하이힐|힐\b|신발|슈즈|sneakers?|shoes?|boots?|sandals?|loafer|heels?/i],
      product_type:'착용형 신발 상품',
      target_customer:'착화감·핏·사이즈·디자인을 보고 신발을 고르는 사용자',
      main_pain_point:'사이즈가 맞을지, 실제 착용 느낌과 디자인이 사진과 같을지 걱정됨',
      core_value:'착화감/핏, 소재/쿠션감, 사이즈/발볼, 실제 착용 장면, 코디',
      spec_hint:'사이즈(발길이/발볼), 소재(겉/안창/밑창), 무게, 색상, 굽 높이, 관리법 확인 필요',
      competitor_hint:'일반 신발 상세는 실제 착용 핏과 사이즈 가이드가 부족할 수 있음',
      sections:['HERO','FIT','DETAIL','FABRIC','COLOR_SIZE','WEAR_SCENE','FAQ','CTA']
    },
    {
      key:'fitness', category_group:'운동/홈트레이닝', template_type:'usage_components',
      patterns:[/저항밴드|튜빙|홈트|운동밴드|요가매트|요가링|폼롤러|덤벨|아령|케틀벨|철봉|악력기|스텝퍼|짐볼|밸런스보드|발란스보드|러닝머신|런닝머신|트레드밀|훌라후프|줄넘기|푸쉬업|푸시업|윗몸|복근|근력|필라테스|헬스|마사지건|마사지볼|스쿼트|코어운동|fitness|workout|resistance|dumbbell|kettlebell/i],
      product_type:'운동/사용법형 상품',
      target_customer:'집에서 간단히 운동하려는 홈트 사용자, 초보 운동자, 공간 부담 없이 운동하고 싶은 사용자',
      main_pain_point:'운동기구는 부피가 크고 사용법이 어렵거나 꾸준히 하기 부담스러움',
      core_value:'공간 절약, 사용법 이해, 구성품 확인, 다양한 동작 활용',
      spec_hint:'구성품, 소재, 강도, 길이, 내하중, 보관 파우치 여부 확인 필요',
      competitor_hint:'저가 운동용품은 구성 설명과 사용법 신뢰가 약할 수 있음',
      sections:['HERO','PROBLEM','COMPONENTS','USAGE','BENEFIT','DETAIL','ROUTINE','CTA']
    },
    {
      // v21.8.24.69: 스포츠/레저(아웃도어) 신설 — 캠핑·낚시·자전거·골프 등은 홈트(fitness)와 달라 야외 사용·구성·휴대 중심.
      key:'sports', category_group:'스포츠/레저', template_type:'usage_components',
      patterns:[/캠핑|텐트|타프|코펠|버너|침낭|등산|트레킹|등산스틱|낚시|낚싯대|자전거|로드바이크|골프|골프채|퍼터|스키|스노보드|서핑보드|스케이트보드|웨이크보드|인라인스케이트|롤러스케이트|스케이트|서핑|라켓|배드민턴|테니스|탁구|축구공|농구공|배구공|야구|글러브|스포츠|레저|아웃도어|킥보드/i],
      product_type:'스포츠/레저 사용형 상품',
      target_customer:'야외 활동·운동을 즐기며 장비의 사용 편의·내구성·휴대성을 보는 사용자',
      main_pain_point:'장비가 무겁거나 설치/휴대가 번거롭고 실제 성능·내구성이 애매할까 걱정됨',
      core_value:'사용 장면, 구성/스펙, 휴대/수납, 내구성, 활용 범위',
      spec_hint:'크기/무게, 소재, 구성품, 수용 인원/대상, 휴대/수납 방식, 사용 환경 확인 필요',
      competitor_hint:'유사 장비는 실제 사용 장면과 휴대/내구 정보가 부족할 수 있음',
      sections:['HERO','PROBLEM','USAGE','COMPONENTS','DETAIL','BENEFIT','FAQ','CTA']
    },
    {
      key:'furniture', category_group:'가구/인테리어', template_type:'space_mood',
      patterns:[/의자|체어|책상|테이블|식탁|침대|매트리스|행거|옷장|서랍장|수납장|책장|선반|장식장|진열장|협탁|화장대|소파|쇼파|스툴|벤치|빈백|좌식|러그|커튼|블라인드|조명|전신거울|파티션|가구|인테리어|chair|desk|table|bed|sofa|shelf|lamp/i],
      product_type:'공간연출형 상품',
      target_customer:'집이나 사무공간 분위기를 개선하고 싶은 홈오피스 사용자, 자취/신혼/소상공인',
      main_pain_point:'실용성은 필요하지만 공간 분위기와 어울리지 않는 제품은 피하고 싶음',
      core_value:'공간 분위기 변화, 소재/디테일, 배치감, 실사용 이미지',
      spec_hint:'사이즈, 소재, 색상, 내하중, 조립 여부 확인 필요',
      competitor_hint:'일반 제품은 공간 연출력과 디테일 설명이 약할 수 있음',
      sections:['HERO','SPACE_PROBLEM','ROOM_MOOD','DETAIL','SIZE_USE','COMPARISON','FAQ','CTA']
    },
    {
      key:'digital_content', category_group:'무형 디지털/전자책/강의/템플릿', template_type:'intangible_offer',
      patterns:[/전자책|이북|e-?book|electronic book|강의|강좌|클래스|온라인\s*강의|원데이\s*클래스|VOD|코칭|컨설팅|템플릿|노션|notion|구독|멤버십|membership|워크북|챌린지|디지털\s*다운로드|pdf\s*자료|강의자료|온라인\s*클래스/i],
      product_type:'무형 디지털 콘텐츠/서비스',
      target_customer:'시간을 아끼고 시행착오를 줄이려는 직장인·사업자·N잡러·초보자',
      main_pain_point:'혼자 정보를 찾아 적용하기 막막하고, 검증 안 된 방법에 시간을 낭비할까 불안함',
      core_value:'바로 적용 가능한 실전 구성, 검증된 결과(비포→애프터), 지속 업데이트·피드백',
      spec_hint:'구성(분량/챕터/템플릿 수), 제공 형식, 업데이트·피드백·커뮤니티 여부, 대상 수준 확인 필요',
      competitor_hint:'일반 전자책/강의는 이론 위주·업데이트 없음·질문 불가일 수 있음',
      sections:['HERO','PROBLEM','SOLUTION','OVERVIEW','BENEFIT','COMPARISON','USAGE','PACKAGE','FAQ','CTA'],
      extra_rule:'무형 상품: 실물 사진이 약하므로 표지/목업/그래프/혜택 카드/타이포 중심으로 시각화. 수익·합격·효과 보장 표현 금지(확인된 후기·만족도 수치만).'
    },
    {
      key:'digital_automation', category_group:'디지털/서비스 패키지', template_type:'workflow_function',
      patterns:[/자동화|마케팅봇|마케팅 봇|블로그봇|블로그 봇|ai 노트북|AI 마케팅|콘텐츠 작성|콘텐츠 운영|업무 자동화|프로그램|풀세팅|풀패키지|네이버블로그|티스토리|쓰레드|쿠팡파트너스|네이버쇼핑커넥트|SNS 콘텐츠|software|automation|dashboard/i],
      product_type:'기능설명형 자동화 상품',
      target_customer:'블로그/SNS/제휴마케팅 콘텐츠 운영을 줄이고 싶은 사장님, 블로그/SNS 운영자, 소상공인',
      main_pain_point:'홍보와 콘텐츠 작업을 매일 직접 하기 번거롭고 시간이 오래 걸림',
      core_value:'반복 작업 흐름 단순화, 포함 프로그램, 세팅 범위, 결과 관리',
      spec_hint:'포함 프로그램, 노트북 사양, 세팅 범위, 지원 범위, 업데이트, 사용 조건 확인 필요',
      competitor_hint:'일반 장비나 툴은 세팅/운영을 사용자가 직접 해야 함',
      sections:['HERO','PAIN_POINT','WORKFLOW','FEATURE','RESULT','PACKAGE','FAQ','CTA']
    },
    {
      key:'digital', category_group:'디지털/가전', template_type:'function_spec',
      patterns:[/노트북|컴퓨터|데스크탑|모니터|태블릿|키보드|마우스|충전기|보조배터리|이어폰|헤드폰|헤드셋|스피커|마이크|웹캠|공유기|프린터|텔레비전|tv\b|냉장고|세탁기|건조기|에어컨|전자레인지|선풍기|가습기|제습기|공기청정기|청소기|드라이기|고데기|면도기|제모기|전동칫솔|가전|디지털|laptop|pc|monitor|charger|tablet/i],
      product_type:'기능/스펙형 상품',
      target_customer:'기능과 스펙을 비교해 합리적으로 구매하려는 사용자',
      main_pain_point:'스펙 차이를 이해하기 어렵고 실제 사용 흐름이 궁금함',
      core_value:'기능, 스펙, 사용 흐름, 호환성, 신뢰 정보',
      spec_hint:'모델명, 크기, 무게, 전원, 호환성, 구성품, 보증 확인 필요',
      competitor_hint:'유사 제품은 스펙은 많지만 실제 사용 이점 설명이 부족할 수 있음',
      sections:['HERO','PAIN_POINT','FEATURE','SPEC','USAGE','TRUST','FAQ','CTA']
    },
    {
      key:'fashion_clothing', category_group:'패션/의류', template_type:'wear_fit',
      patterns:[/티셔츠|티셔트|후드티|후드집업|맨투맨|니트|스웨터|가디건|블라우스|셔츠|남방|바지|팬츠|청바지|데님|슬랙스|반바지|조거|레깅스|치마|스커트|원피스|드레스|자켓|재킷|점퍼|패딩|코트|조끼|정장|트레이닝복|츄리닝|잠옷|파자마|수영복|비키니|래쉬가드|속옷|언더웨어|민소매|나시|아우터|플리스|후리스|의류|옷|wear|shirt|pants|hoodie|knit|jacket|coat|dress|leggings/i],
      product_type:'착용형 상품',
      target_customer:'워터파크, 수영장, 바캉스에서 노출 부담은 줄이고 편하게 입을 물놀이 옷을 찾는 고객',
      main_pain_point:'몸매가 너무 드러날까 걱정되고 상하의 코디를 따로 맞추기 번거로움',
      core_value:'노출 부담을 줄이는 착용 인상, 세트 코디 편의성, 확인된 컬러와 활동 장면',
      spec_hint:'사이즈, 소재, 세탁법, 컬러, 모델 정보 확인 필요',
      competitor_hint:'일반 의류 상세페이지는 핏과 실착 정보가 부족할 수 있음',
      sections:['HERO','FIT','FABRIC','DETAIL','COLOR_SIZE','WEAR_SCENE','FAQ','CTA']
    },
    {
      key:'fashion_accessory', category_group:'패션잡화', template_type:'detail_lifestyle',
      patterns:[/지갑|장지갑|반지갑|명함지갑|카드지갑|동전지갑|가방|백팩|배낭|토트백|크로스백|숄더백|에코백|클러치|미니백|핸드백|벨트|모자|캡모자|비니|버킷햇|양말|스타킹|장갑|머플러|목도리|스카프|넥타이|선글라스|안경테|손목시계|목걸이|귀걸이|반지|팔찌|주얼리|악세서리|머리끈|헤어밴드|헤어핀|스크런치|키링|키홀더|파우치|케이스|wallet|bag|backpack|belt|cap|watch|necklace|case/i],
      product_type:'디테일/휴대형 상품',
      target_customer:'상담, 계약, 미팅, 출근 전 명함이나 카드를 꺼내는 순간이 신경 쓰이는 직장인·자영업자',
      main_pain_point:'지갑 속에서 명함이 구겨지거나 카드와 섞여 필요한 순간 바로 꺼내기 불편함',
      core_value:'명함을 따로 정리하는 준비감, 손에 잡히는 휴대성, 업무 자리에서 자연스러운 사용 장면, 선물하기 쉬운 무난함',
      spec_hint:'소재, 크기, 수납 칸, 색상 옵션, 제조국, 구성품 확인 필요',
      competitor_hint:'비슷한 잡화는 명함을 꺼내는 순간의 불편과 실제 수납 장면 설명이 부족할 수 있음',
      sections:['HERO','PROBLEM','SOLUTION','DETAIL','SPEC','LIFESTYLE','FAQ','CTA']
    },
    {
      key:'beauty', category_group:'뷰티/화장품/바디', template_type:'mood_texture',
      patterns:[/화장품|스킨케어|크림|로션|세럼|에센스|앰플|토너|미스트|향수|퍼퓸|바디|바디워시|바디로션|클렌저|클렌징|폼클렌징|샴푸|린스|트리트먼트|헤어오일|헤어팩|립스틱|립밤|틴트|쿠션|파운데이션|컨실러|프라이머|마스카라|아이라이너|아이섀도|섀도|블러셔|마스크팩|시트마스크|선크림|선블록|네일|매니큐어|필링|스크럽|핸드크림|아이크림|하이라이터|아이브로우|브로우펜슬|아이펜슬|섀딩|컨투어|글리터|피그먼트|뷰러|메이크업|아이메이크업|펜슬|뷰티|beauty|cream|lotion|serum|toner|essence|mask|cushion|tint|perfume|body|makeup|pencil/i],
      product_type:'감성/텍스처형 상품',
      target_customer:'무드, 향, 사용감, 구성과 피부 표현을 신중히 보는 사용자',
      main_pain_point:'사용감과 향, 제형이 나에게 맞을지 구매 전 알기 어려움',
      core_value:'무드컷, 텍스처, 향/성분 포인트, 사용감, 구성',
      spec_hint:'용량, 전성분, 향, 제형, 사용법, 주의사항 확인 필요',
      competitor_hint:'일반 뷰티 상품은 제형과 무드가 충분히 전달되지 않을 수 있음',
      sections:['HERO','MOOD','TEXTURE','POINT','HOW_TO_USE','COLLECTION','FAQ','CTA']
    },
    {
      key:'living', category_group:'생활용품/청소/수납', template_type:'problem_solution',
      patterns:[/청소|수납|욕실|화장실|세탁|빨래|건조대|생활용품|정리함|옷걸이|휴지|물티슈|타월|수건|행주|수세미|고무장갑|매트|발매트|클리너|밀대|대걸레|빗자루|쓰레기통|쓰레받기|제습제|탈취|방충|모기|벌레|먼지|곰팡이|배수구|압축팩|진공팩|디퓨저|향초|clean|storage|bath|laundry/i],
      product_type:'생활 문제해결형 상품',
      target_customer:'생활 속 불편을 줄이고 정리/위생을 개선하고 싶은 사용자',
      main_pain_point:'일상에서 반복되는 작은 불편을 간단히 해결하고 싶음',
      core_value:'생활 불편 해결, 사용 전후, 보관/위생, 반복 사용',
      spec_hint:'크기, 소재, 구성, 설치/사용 방법, 세척 가능 여부 확인 필요',
      competitor_hint:'유사 생활용품은 실제 사용 장면과 전후 설명이 부족할 수 있음',
      sections:['HERO','PROBLEM','SOLUTION','HOW_TO_USE','BEFORE_AFTER','DETAIL','FAQ','CTA']
    },
    {
      key:'kitchen', category_group:'주방/식기/조리도구', template_type:'use_clean_storage',
      patterns:[/주방|컵\b|머그|텀블러|보온병|그릇|접시|냄비|프라이팬|도마|밀폐용기|반찬통|보관용기|식기|수저|숟가락|젓가락|포크|주전자|도시락|믹서기|블렌더|에어프라이어|전기포트|밥솥|국자|뒤집개|채반|트레이|쟁반|찜기|위생장갑|키친타올|조리|kitchen|cup|tumbler|pan|pot|container/i],
      product_type:'주방 사용형 상품',
      target_customer:'사용 편의, 세척, 보관, 소재 안정감을 보는 사용자',
      main_pain_point:'주방용품은 실제 사용감과 세척/보관이 불편할까 걱정됨',
      core_value:'사용 장면, 소재/위생, 용량/크기, 세척/보관',
      spec_hint:'용량, 크기, 소재, 열원/식기세척기 가능 여부 확인 필요',
      competitor_hint:'일반 주방용품은 실사용과 보관 정보가 부족할 수 있음',
      sections:['HERO','USE_SCENE','MATERIAL','SIZE','CLEANING','STORAGE','FAQ','CTA']
    },
    {
      key:'food', category_group:'식품/간식/음료', template_type:'taste_package',
      patterns:[/간식|커피|원두|녹차|홍차|보이차|우롱차|유자차|현미차|둥굴레차|밀크티|티백|음료|식품|과자|쿠키|초콜릿|초콜렛|사탕|젤리|디저트|빵\b|떡\b|만두|어묵|소스|라면|즉석밥|밀키트|반찬|김치|육포|견과|시리얼|오트밀|닭가슴살|프로틴|단백질|영양제|비타민|유산균|프로바이오틱스|홍삼|오메가3|루테인|콜라겐|아연|마그네슘|비오틴|밀크씨슬|밀크시슬|쏘팔메토|글루코사민|프로폴리스|코엔자임|보충제|건강즙|꿀\b|잼\b|시럽|참기름|들기름|곡물|선식|미숫가루|즙\b|진액|건강기능식품|에너지바|food|coffee|tea|snack|drink|protein|vitamin/i],
      product_type:'식품/맛 경험형 상품',
      target_customer:'맛, 구성, 섭취 상황, 보관 편의를 보고 선택하는 사용자',
      main_pain_point:'맛과 구성, 보관 방식이 기대와 다를까 걱정됨',
      core_value:'맛/상황, 원재료/구성, 섭취 장면, 보관',
      spec_hint:'중량, 구성, 원재료, 유통기한, 보관방법, 알레르기 정보 확인 필요',
      competitor_hint:'비슷한 식품은 맛의 상황성과 구성 설명이 약할 수 있음',
      sections:['HERO','TASTE_SCENE','PACKAGE','INGREDIENT','HOW_TO_EAT','STORAGE','FAQ','CTA'],
      extra_rule:'건강 관련 과장 표현, 의사/병원/전문의 표현 절대 금지'
    },
    {
      key:'pet', category_group:'반려동물용품', template_type:'pet_use_safety',
      patterns:[/강아지|고양이|반려|애견|애묘|펫\b|사료|간식|츄르|개껌|캣타워|스크래쳐|스크래처|리드줄|목줄|하네스|급수기|급식기|자동급식|배변패드|배변|펫모래|고양이모래|낚싯대장난감|이동가방|켄넬|캣휠|노즈워크|발톱깎이|펫샴푸|pet|cat|dog/i],
      product_type:'반려생활 사용형 상품',
      target_customer:'반려동물의 사용 편의와 관리/세척/안전 확인을 원하는 보호자',
      main_pain_point:'우리 반려동물에게 맞을지, 관리가 쉬울지 걱정됨',
      core_value:'사용 장면, 대상 크기, 관리/세척, 소재 확인',
      spec_hint:'대상 크기, 소재, 세척 방법, 구성품, 주의사항 확인 필요',
      competitor_hint:'유사 반려용품은 실제 사용 대상과 관리 정보가 부족할 수 있음',
      sections:['HERO','PET_PROBLEM','USE_SCENE','DETAIL','CLEANING','SIZE_TARGET','FAQ','CTA']
    },
    {
      key:'kids', category_group:'유아/키즈', template_type:'parent_trust',
      patterns:[/유아|아기|영유아|신생아|키즈|어린이|아동|장난감|완구|블록|퍼즐|학습|교구|육아|베이비|기저귀|분유|젖병|이유식|유모차|카시트|보행기|아기띠|치발기|쏘서|바운서|모빌|턱받이|kids|baby|toy|infant/i],
      product_type:'유아/키즈 신뢰형 상품',
      target_customer:'아이 사용 환경과 관리 편의, 구성 안전성을 확인하려는 부모',
      main_pain_point:'아이에게 맞는지, 관리가 쉬운지, 구성품이 안전하게 보이는지 걱정됨',
      core_value:'부모 고민, 사용 장면, 소재/관리, 구성품, 주의사항',
      spec_hint:'연령, 소재, 크기, 구성품, KC 등 확인된 인증 여부 확인 필요',
      competitor_hint:'유사 제품은 연령/소재/관리 정보가 부족할 수 있음',
      sections:['HERO','PARENT_PROBLEM','USE_SCENE','MATERIAL','COMPONENTS','CARE','FAQ','CTA']
    },
    {
      key:'auto', category_group:'자동차/차량용품', template_type:'install_before_after',
      patterns:[/자동차|차량|차박|세차|블랙박스|타이어|엔진오일|워셔액|성에제거|틴팅|썬팅|방향제|거치대|핸들커버|시트커버|차량매트|햇빛가리개|썬바이저|트렁크|와이퍼|인버터|점프스타터|하이패스|car|auto|vehicle|tire/i],
      product_type:'차량 문제해결형 상품',
      target_customer:'차량 안팎의 불편을 줄이고 설치/사용 편의를 원하는 운전자',
      main_pain_point:'차량용품은 호환과 설치가 어렵거나 실제 효과가 애매할까 걱정됨',
      core_value:'차량 내 불편 해결, 설치/사용, 전후 비교, 호환/크기',
      spec_hint:'차종 호환, 크기, 설치 방법, 구성품, 주의사항 확인 필요',
      competitor_hint:'유사 차량용품은 호환성과 설치 설명이 부족할 수 있음',
      sections:['HERO','CAR_PROBLEM','INSTALL','BEFORE_AFTER','DETAIL','COMPATIBILITY','FAQ','CTA']
    },
    {
      key:'stationery', category_group:'문구/사무/취미', template_type:'use_detail_components',
      patterns:[/문구|볼펜|연필|색연필|만년필|샤프|지우개|형광펜|마커펜|다이어리|플래너|캘린더|노트북다이어리|메모지|포스트잇|스티커|마스킹테이프|스탬프|가위|풀\b|파일철|바인더|필통|클립|라벨지|화이트보드|독서대|책갈피|스케치북|물감|색칠|클레이|비즈|뜨개|자수|공예|취미|사무용품|stationery|pen|diary|sticker|craft/i],
      product_type:'문구/취미 활용형 상품',
      target_customer:'디테일, 구성, 활용 예시, 보관/선물감을 보는 사용자',
      main_pain_point:'작은 제품일수록 실제 구성과 활용성이 구매 전 잘 보이지 않음',
      core_value:'사용 상황, 디테일, 구성, 활용 예시, 보관',
      spec_hint:'크기, 소재, 구성, 색상, 사용 방법 확인 필요',
      competitor_hint:'유사 문구/취미 상품은 실제 활용 예시가 부족할 수 있음',
      sections:['HERO','USE_SCENE','DETAIL','COMPONENTS','EXAMPLES','STORAGE','FAQ','CTA']
    },
    {
      // v21.8.24.69: 도서/음반/DVD 신설 — 내용/구성/실물 상태 중심. (책을 의류/일반으로 오분류하던 문제 해결)
      key:'media', category_group:'도서/음반/DVD', template_type:'intangible_offer',
      patterns:[/도서|서적|소설|에세이|시집|자기계발|문제집|수험서|참고서|교재|만화책|그림책|동화책|위인전|레시피북|요리책|음반|앨범|\bcd\b|\blp\b|바이닐|블루레이|\bdvd\b|화보집/i],
      product_type:'도서/콘텐츠형 상품',
      target_customer:'내용·구성·저자(아티스트)와 실물 상태를 보고 고르는 독자/소비자',
      main_pain_point:'내용이 기대와 다를까, 구성/분량/실물 상태가 궁금함',
      core_value:'핵심 내용 소개, 목차/구성, 추천 대상, 실물/구성 확인',
      spec_hint:'페이지/분량, 구성(권수/디스크 수), 출간/발매일, 대상 독자, 판형/포맷 확인 필요',
      competitor_hint:'유사 도서/음반은 핵심 내용과 추천 대상 설명이 부족할 수 있음',
      sections:['HERO','PROBLEM','SOLUTION','OVERVIEW','BENEFIT','PACKAGE','FAQ','CTA'],
      extra_rule:'내용 과장·합격/수익 보장 표현 금지. 표지/실물은 원본 기준만 사용, 가짜 수상/베스트셀러 배지 생성 금지.'
    }
  ];

  function cleanAnalyzerNoise(text=''){
    return String(text || '')
      .replace(/component\s*=\s*전체[^\n]*/gi, ' ')
      .replace(/상품페이지 옵션 후보[^\n]*/gi, ' ')
      .replace(/추천상품|함께 본 상품|다른 고객이 함께|카테고리|전체\/패션의류[^\n]*/gi, ' ')
      .replace(/패션의류 잡화\/뷰티\/출산 유아동\/식품\/주방용품\/생활용품\/홈인테리어\/가전디지털\/스포츠 레저\/자동차용품\/도서 음반 DVD/gi, ' ')
      .replace(/생활가전\s+청소기\s+계절가전\s+뷰티\/?헤어가전\s+건강가전\s+주방가전\s+데스크탑\s+모니터\s+휴대폰\s+태블릿PC\s+스마트워치\/?밴드\s+게임/gi, ' ')
      .replace(/회사소개\s+Investor\s+Relations\s+인재채용\s+입점/gi, ' ')
      .replace(/정격\s*세탁\s*:?\s*기\/?건조기/gi, ' ');
  }

  function fieldText(...values){
    return cleanAnalyzerNoise(values.filter(Boolean).join(' ')).toLowerCase();
  }

  function cleanSpecHint(value=''){
    const lines = String(value || '').split(/\n+/)
      .map(v => cleanAnalyzerNoise(v).replace(/\s+/g, ' ').trim())
      .filter(Boolean)
      .filter(v => !/component\s*=|전체\/패션의류|홈인테리어|가전디지털|추천상품|함께 본 상품|다른 고객/i.test(v));
    return [...new Set(lines)].slice(0, 20).join('\n');
  }

  function scoreRule(rule, data={}){
    const strongText = fieldText(data.product, data.category);
    const weakText = fieldText(data.benefits, data.pain, data.specs, data.competitor, data.link, data.platform);
    let score = 0;
    for (const re of rule.patterns) {
      try {
        if (re.test(strongText)) score += 100;
        re.lastIndex = 0;
        if (re.test(weakText)) score += 12;
        re.lastIndex = 0;
      } catch (_) {}
    }
    // v21.8.24.2: 상품명에 강한 의류 키워드가 있으면, 쿠팡 카테고리/추천상품 잡음보다 우선한다.
    if (rule.key === 'fashion_clothing' && /래쉬가드|수영복|rashguard|비치팬츠|레깅스|티셔츠|팬츠|의류|옷/.test(strongText)) score += 80;
    if (rule.key === 'fashion_clothing' && /명함지갑|카드지갑|지갑|케이스|파우치|가방/.test(strongText)) score -= 80;
    if (rule.key === 'fashion_accessory' && /명함지갑|카드지갑|지갑|명함 케이스|명함케이스|케이스|파우치|가방|벨트/.test(strongText)) score += 90;
    if (rule.key === 'furniture' && !/의자|체어|책상|테이블|식탁|침대|매트리스|행거|옷장|서랍장|수납장|책장|선반|장식장|진열장|협탁|화장대|소파|쇼파|스툴|벤치|빈백|러그|커튼|블라인드|조명|전신거울|파티션|chair|desk|table|bed|sofa|shelf|lamp/.test(strongText)) score -= 35;
    // v21.8.24.67: 노트북/PC/태블릿을 '모델명·사양'으로도 인식. '옴니북·그램·갤럭시북·맥북' 등 모델명엔 '노트북' 단어가
    //  없어 general(감성 구조, SPEC 없음)로 빠지던 문제 수정 → 브랜드 모델/사양 토큰이 있으면 사양형 digital(function_spec)로.
    const deviceModelRe = /옴니북|omnibook|갤럭시북|galaxy\s*book|맥북|macbook|씽크패드|thinkpad|아이디어패드|ideapad|젠북|zenbook|비보북|vivobook|크롬북|chromebook|울트라북|ultrabook|서피스|surface|아이패드|ipad|갤럭시탭|galaxy\s*tab|리전|legion|빅터스|victus|\bgram\b|그램\s|\brog\b|\btuf\b|expertbook|프로북|probook|엘리트북|elitebook|파빌리온|pavilion/i;
    const deviceSpecRe = /인텔|intel|라이젠|ryzen|core\s*i?\d|코어\s*울트라|ultra\s*[579]|스냅드래곤|snapdragon|\bm[1-4]\s*(칩|chip|pro|max)?\b|\bssd\b|nvme|ddr\d|wi-?fi\s*\d|\bnpu\b|\d{2,3}\s*인치|oled|qhd|윈도우\s*1[01]|windows\s*1[01]/i;
    const accessoryRe = /케이스|파우치|커버|거치대|스탠드|보호필름|필름|스킨|그립|악세|어댑터|허브|독스테이션|마우스패드|키스킨|받침대|쿨러|보호\s*케이스/i;
    const automationServiceRe = /자동화|블로그봇|블로그 봇|마케팅봇|마케팅 봇|쿠팡파트너스|네이버쇼핑커넥트|풀세팅|풀패키지|업무 자동화|automation/i;
    const isHardwareDevice = (deviceModelRe.test(strongText) || deviceSpecRe.test(strongText)) && !accessoryRe.test(strongText);
    if (rule.key === 'digital' && isHardwareDevice) score += 170;
    if (rule.key === 'digital_automation' && deviceModelRe.test(strongText) && !automationServiceRe.test(`${strongText} ${weakText}`)) score -= 200;
    // v21.8.24.68: '신발'은 신발 자체일 때만 footwear. 관리/세탁/클리너 등 케어 제품은 shoe_care/living가 우선.
    if (rule.key === 'footwear' && /구두약|광택|슈케어|클리너|크림|방수스프레이|세탁|세제|탈취|관리|건조기/.test(strongText)) score -= 140;
    // v21.8.24.91: 유아/아기/베이비 맥락의 물티슈·티슈 등은 생활용품(청소)이 아니라 유아용품(kids)으로 — 차가운 무드 방지.
    const babyCtxRe = /유아|아기|영유아|신생아|베이비|baby|키즈|이유식|기저귀|분유|젖병/i;
    if (rule.key === 'kids' && babyCtxRe.test(strongText)) score += 130;
    if (rule.key === 'living' && babyCtxRe.test(strongText)) score -= 90;
    // v21.8.24.77: '아트클래스' 같은 브랜드의 '클래스'가 온라인강의(digital_content)로 오분류되는 문제 수정 —
    //  화장품/메이크업 키워드가 있으면 물리 화장품(beauty)으로 강하게 보정.
    const cosmeticRe = /하이라이터|아이브로우|브로우\s*펜슬|아이\s*펜슬|섀딩|컨투어|글리터|피그먼트|뷰러|마스카라|아이라이너|아이섀도|섀도|틴트|립스틱|립밤|쿠션|파운데이션|컨실러|블러셔|메이크업|아이\s*메이크업|쉬머|루스\s*파우더|팩트|선크림|선블록|크림|세럼|토너|에센스|앰플|화장품/i;
    if (rule.key === 'beauty' && cosmeticRe.test(`${strongText} ${weakText}`)) score += 150;
    if ((rule.key === 'digital_content' || rule.key === 'digital') && cosmeticRe.test(`${strongText} ${weakText}`)) score -= 170;
    // v21.8.24.13: 자동화 노트북/프로그램 풀세팅 패키지는 일반 노트북보다 서비스 패키지로 우선 분류한다.
    const allText = `${strongText} ${weakText}`;
    const automationPackageRe = /자동화|블로그봇|블로그 봇|마케팅봇|마케팅 봇|티스토리|쓰레드|쿠팡파트너스|네이버쇼핑커넥트|SNS\s*콘텐츠|콘텐츠\s*운영|풀세팅|풀패키지|프로그램|업무 자동화|dashboard|automation/i;
    if (rule.key === 'digital_automation' && automationPackageRe.test(allText)) score += 180;
    if (rule.key === 'digital' && automationPackageRe.test(allText)) score -= 85;
    if (rule.key === 'digital_automation' && /노트북|laptop|pc|컴퓨터/.test(strongText) && automationPackageRe.test(allText)) score += 80;
    // v21.8.24.33: 무형 디지털 콘텐츠(전자책/강의/코칭/템플릿)는 가전·자동화 패키지보다 무형 상품으로 우선 분류.
    const intangibleRe = /전자책|이북|e-?book|강의|강좌|클래스|코칭|컨설팅|템플릿|노션|notion|구독|멤버십|워크북|챌린지|VOD|pdf\s*자료|강의자료/i;
    // 전자책/강의/코칭/템플릿 같은 '무형 명사'는 제품 정체성이므로, 주제어(자동화 등)보다 우선한다.
    const intangibleNounRe = /전자책|이북|e-?book|강의|강좌|클래스|코칭|컨설팅|템플릿|노션|구독|멤버십|워크북|VOD|강의자료/i;
    if (rule.key === 'digital_content' && intangibleRe.test(strongText)) score += 180;
    if ((rule.key === 'digital' || rule.key === 'digital_automation') && intangibleNounRe.test(strongText)) score -= 130;
    // v21.8.24.46: 손/미니/휴대/핸디/넥 선풍기 등 '계절·감성 소비재'는 가전(tech)이 아니라 생활 문제해결형으로 분류
    //  → 기계적 테크 무드 대신 시원/감성 무드 + 팔리는 문제해결 흐름이 적용되게 한다.
    const seasonalGadgetRe = /(손|미니|휴대용?|핸디|넥밴드?|탁상|목걸이)\s*선풍기|넥쿨러|손\s*풍기|미니\s*가습기|휴대용?\s*가습기/i;
    if (rule.key === 'digital' && seasonalGadgetRe.test(strongText)) score -= 130;
    if (rule.key === 'living' && seasonalGadgetRe.test(strongText)) score += 130;
    return score;
  }

  // v21.8.24.31: 관여도(저관여/고관여) 판정. 가격이 핵심이고, 중간가는 카테고리로 보정.
  // 저관여 = 부담 적은 저가/소모/생활/잡화 → 긴 스토리텔링 대신 사회적증거·옵션·활용 중심.
  const LOW_INVOLVE_CATS = ['living','kitchen','food','stationery','shoe_care','fashion_accessory'];
  const HIGH_INVOLVE_CATS = ['furniture','digital','digital_automation','beauty'];
  function judgeInvolvement(key, data){
    const price = parseInt(String(data && data.price || '').replace(/[^\d]/g, ''), 10) || 0;
    if(price > 0){
      if(price < 15000) return 'low';
      if(price >= 40000) return 'high';
      return LOW_INVOLVE_CATS.indexOf(key) >= 0 ? 'low' : 'high'; // 1.5만~4만: 카테고리로 결정
    }
    if(HIGH_INVOLVE_CATS.indexOf(key) >= 0) return 'high';
    if(LOW_INVOLVE_CATS.indexOf(key) >= 0) return 'low';
    return 'high'; // 가격 불명 + 중립 카테고리 → 기존 스토리텔링 유지(안전)
  }

  function analyzeProductContext(data={}){
    const ranked = RULES
      .map(rule => ({ rule, score: scoreRule(rule, data) }))
      .filter(x => x.score > 0)
      .sort((a, b) => b.score - a.score);
    let found = ranked[0]?.rule;
    let score = ranked[0]?.score || 0;
    if(!found){
      found = {
        key:'general', category_group:'일반상품/자동판단 필요', template_type:'general_dynamic',
        product_type:'일반 상세페이지 상품',
        target_customer:'상품 이미지와 링크를 보고 구매를 검토하는 사용자',
        main_pain_point:'상품의 실제 형태, 사용법, 구성, 구매 이유를 빠르게 확인하고 싶음',
        core_value:'제품 정체성, 사용 장면, 디테일, 구성, 구매저항 해소',
        spec_hint:'상품명, 구성품, 소재/크기/사용법 확인 필요',
        competitor_hint:'유사 상품 대비 핵심 차별점 확인 필요',
        sections:['HERO','PROBLEM','OVERVIEW','DETAIL','USAGE','BENEFIT','FAQ','CTA']
      };
    }
    return {
      key: found.key,
      product_type: found.product_type,
      category_group: found.category_group,
      template_type: found.template_type,
      target_customer: data.target || found.target_customer,
      main_pain_point: data.pain || found.main_pain_point,
      core_value: data.benefits || found.core_value,
      spec_hint: cleanSpecHint(data.specs) || found.spec_hint,
      competitor_hint: data.competitor || found.competitor_hint,
      recommended_sections: found.sections.slice(),
      extra_rule: found.extra_rule || '',
      involvement: judgeInvolvement(found.key, data),
      confidence: found.key==='general' ? 45 : Math.min(95, Math.max(72, 68 + Math.round(score / 4)))
    };
  }

  window.DP_PRODUCT_ANALYZER = { analyzeProductContext, RULES };
})();
