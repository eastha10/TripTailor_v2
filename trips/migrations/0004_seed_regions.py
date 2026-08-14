from django.db import migrations


REGIONS = [
    # 특별시 / 광역시 / 특별자치시
    ("11", "", "서울특별시", "Seoul"),
    ("26", "", "부산광역시", "Busan"),
    ("27", "", "대구광역시", "Daegu"),
    ("28", "", "인천광역시", "Incheon"),
    ("30", "", "대전광역시", "Daejeon"),
    ("31", "", "울산광역시", "Ulsan"),
    ("36110", "", "세종특별자치시", "Sejong"),

    # 광주 예외
    # 실제 관광지 조회 시 12/""을 그대로 사용하지 않고
    # 동구(210), 서구(240), 남구(270), 북구(300), 광산구(330)를 각각 호출
    ("12", "", "광주광역시", "Gwangju"),

    # 전남
    ("12", "110", "목포시", "Mokpo"),
    ("12", "130", "여수시", "Yeosu"),
    ("12", "150", "순천시", "Suncheon"),
    ("12", "170", "나주시", "Naju"),
    ("12", "190", "광양시", "Gwangyang"),
    ("12", "710", "담양군", "Damyang"),
    ("12", "720", "곡성군", "Gokseong"),
    ("12", "730", "구례군", "Gurye"),
    ("12", "740", "고흥군", "Goheung"),
    ("12", "750", "보성군", "Boseong"),
    ("12", "760", "화순군", "Hwasun"),
    ("12", "770", "장흥군", "Jangheung"),
    ("12", "780", "강진군", "Gangjin"),
    ("12", "790", "해남군", "Haenam"),
    ("12", "800", "영암군", "Yeongam"),
    ("12", "810", "무안군", "Muan"),
    ("12", "820", "함평군", "Hampyeong"),
    ("12", "830", "영광군", "Yeonggwang"),
    ("12", "840", "장성군", "Jangseong"),
    ("12", "850", "완도군", "Wando"),
    ("12", "860", "진도군", "Jindo"),
    ("12", "870", "신안군", "Sinan"),

    # 대구 - 군 단위
    ("27", "710", "달성군", "Dalseong"),
    ("27", "720", "군위군", "Gunwi"),

    # 인천 - 군 단위
    ("28", "710", "강화군", "Ganghwa"),
    ("28", "720", "옹진군", "Ongjin"),

    # 경기도
    ("41", "110", "수원시", "Suwon"),
    ("41", "130", "성남시", "Seongnam"),
    ("41", "150", "의정부시", "Uijeongbu"),
    ("41", "170", "안양시", "Anyang"),
    ("41", "190", "부천시", "Bucheon"),
    ("41", "210", "광명시", "Gwangmyeong"),
    ("41", "220", "평택시", "Pyeongtaek"),
    ("41", "250", "동두천시", "Dongducheon"),
    ("41", "270", "안산시", "Ansan"),
    ("41", "280", "고양시", "Goyang"),
    ("41", "290", "과천시", "Gwacheon"),
    ("41", "310", "구리시", "Guri"),
    ("41", "360", "남양주시", "Namyangju"),
    ("41", "370", "오산시", "Osan"),
    ("41", "390", "시흥시", "Siheung"),
    ("41", "410", "군포시", "Gunpo"),
    ("41", "430", "의왕시", "Uiwang"),
    ("41", "450", "하남시", "Hanam"),
    ("41", "460", "용인시", "Yongin"),
    ("41", "480", "파주시", "Paju"),
    ("41", "500", "이천시", "Icheon"),
    ("41", "550", "안성시", "Anseong"),
    ("41", "570", "김포시", "Gimpo"),
    ("41", "590", "화성시", "Hwaseong"),
    ("41", "610", "광주시", "Gwangju"),
    ("41", "630", "양주시", "Yangju"),
    ("41", "650", "포천시", "Pocheon"),
    ("41", "670", "여주시", "Yeoju"),
    ("41", "800", "연천군", "Yeoncheon"),
    ("41", "820", "가평군", "Gapyeong"),
    ("41", "830", "양평군", "Yangpyeong"),

    # 충청북도
    ("43", "110", "청주시", "Cheongju"),
    ("43", "130", "충주시", "Chungju"),
    ("43", "150", "제천시", "Jecheon"),
    ("43", "720", "보은군", "Boeun"),
    ("43", "730", "옥천군", "Okcheon"),
    ("43", "740", "영동군", "Yeongdong"),
    ("43", "745", "증평군", "Jeungpyeong"),
    ("43", "750", "진천군", "Jincheon"),
    ("43", "760", "괴산군", "Goesan"),
    ("43", "770", "음성군", "Eumseong"),
    ("43", "800", "단양군", "Danyang"),

    # 충청남도
    ("44", "130", "천안시", "Cheonan"),
    ("44", "150", "공주시", "Gongju"),
    ("44", "180", "보령시", "Boryeong"),
    ("44", "200", "아산시", "Asan"),
    ("44", "210", "서산시", "Seosan"),
    ("44", "230", "논산시", "Nonsan"),
    ("44", "250", "계룡시", "Gyeryong"),
    ("44", "270", "당진시", "Dangjin"),
    ("44", "710", "금산군", "Geumsan"),
    ("44", "760", "부여군", "Buyeo"),
    ("44", "770", "서천군", "Seocheon"),
    ("44", "790", "청양군", "Cheongyang"),
    ("44", "800", "홍성군", "Hongseong"),
    ("44", "810", "예산군", "Yesan"),
    ("44", "825", "태안군", "Taean"),

    # 경상북도
    ("47", "110", "포항시", "Pohang"),
    ("47", "130", "경주시", "Gyeongju"),
    ("47", "150", "김천시", "Gimcheon"),
    ("47", "170", "안동시", "Andong"),
    ("47", "190", "구미시", "Gumi"),
    ("47", "210", "영주시", "Yeongju"),
    ("47", "230", "영천시", "Yeongcheon"),
    ("47", "250", "상주시", "Sangju"),
    ("47", "280", "문경시", "Mungyeong"),
    ("47", "290", "경산시", "Gyeongsan"),
    ("47", "730", "의성군", "Uiseong"),
    ("47", "750", "청송군", "Cheongsong"),
    ("47", "760", "영양군", "Yeongyang"),
    ("47", "770", "영덕군", "Yeongdeok"),
    ("47", "820", "청도군", "Cheongdo"),
    ("47", "830", "고령군", "Goryeong"),
    ("47", "840", "성주군", "Seongju"),
    ("47", "850", "칠곡군", "Chilgok"),
    ("47", "900", "예천군", "Yecheon"),
    ("47", "920", "봉화군", "Bonghwa"),
    ("47", "930", "울진군", "Uljin"),
    ("47", "940", "울릉군", "Ulleung"),

    # 경상남도
    ("48", "120", "창원시", "Changwon"),
    ("48", "170", "진주시", "Jinju"),
    ("48", "220", "통영시", "Tongyeong"),
    ("48", "240", "사천시", "Sacheon"),
    ("48", "250", "김해시", "Gimhae"),
    ("48", "270", "밀양시", "Miryang"),
    ("48", "310", "거제시", "Geoje"),
    ("48", "330", "양산시", "Yangsan"),
    ("48", "720", "의령군", "Uiryeong"),
    ("48", "730", "함안군", "Haman"),
    ("48", "740", "창녕군", "Changnyeong"),
    ("48", "820", "고성군", "Goseong"),
    ("48", "840", "남해군", "Namhae"),
    ("48", "850", "하동군", "Hadong"),
    ("48", "860", "산청군", "Sancheong"),
    ("48", "870", "함양군", "Hamyang"),
    ("48", "880", "거창군", "Geochang"),
    ("48", "890", "합천군", "Hapcheon"),

    # 제주특별자치도
    ("50", "110", "제주시", "Jeju"),
    ("50", "130", "서귀포시", "Seogwipo"),

    # 강원특별자치도
    ("51", "110", "춘천시", "Chuncheon"),
    ("51", "130", "원주시", "Wonju"),
    ("51", "150", "강릉시", "Gangneung"),
    ("51", "170", "동해시", "Donghae"),
    ("51", "190", "태백시", "Taebaek"),
    ("51", "210", "속초시", "Sokcho"),
    ("51", "230", "삼척시", "Samcheok"),
    ("51", "720", "홍천군", "Hongcheon"),
    ("51", "730", "횡성군", "Hoengseong"),
    ("51", "750", "영월군", "Yeongwol"),
    ("51", "760", "평창군", "Pyeongchang"),
    ("51", "770", "정선군", "Jeongseon"),
    ("51", "780", "철원군", "Cheorwon"),
    ("51", "790", "화천군", "Hwacheon"),
    ("51", "800", "양구군", "Yanggu"),
    ("51", "810", "인제군", "Inje"),
    ("51", "820", "고성군", "Goseong"),
    ("51", "830", "양양군", "Yangyang"),

    # 전북특별자치도
    ("52", "110", "전주시", "Jeonju"),
    ("52", "130", "군산시", "Gunsan"),
    ("52", "140", "익산시", "Iksan"),
    ("52", "180", "정읍시", "Jeongeup"),
    ("52", "190", "남원시", "Namwon"),
    ("52", "210", "김제시", "Gimje"),
    ("52", "710", "완주군", "Wanju"),
    ("52", "720", "진안군", "Jinan"),
    ("52", "730", "무주군", "Muju"),
    ("52", "740", "장수군", "Jangsu"),
    ("52", "750", "임실군", "Imsil"),
    ("52", "770", "순창군", "Sunchang"),
    ("52", "790", "고창군", "Gochang"),
    ("52", "800", "부안군", "Buan"),
]


def seed_regions(apps, schema_editor):
    Region = apps.get_model("trips", "Region")

    for regn_code, signgu_code, name, name_en in REGIONS:
        Region.objects.update_or_create(
            l_dong_regn_code=regn_code,
            l_dong_signgu_code=signgu_code,
            defaults={
                "name": name,
                "name_en": name_en,
            },
        )


def remove_regions(apps, schema_editor):
    Region = apps.get_model("trips", "Region")

    for regn_code, signgu_code, _, _ in REGIONS:
        Region.objects.filter(
            l_dong_regn_code=regn_code,
            l_dong_signgu_code=signgu_code,
        ).delete()


class Migration(migrations.Migration):

    dependencies = [
        (
            "trips",
            "0003_remove_region_area_code_region_l_dong_regn_code_and_more",
        ),
    ]

    operations = [
        migrations.RunPython(
            seed_regions,
            remove_regions,
        ),
    ]