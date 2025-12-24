# Schema Keywords - Anahtar kelimeler

# Bu kısım manuel olarak veri tabanına özel olarak eklenmelidir...

SCHEMA_KEYWORDS = {
    "e_sayac": {
        "table_keywords": [
            "sayaç", "elektrik sayacı", "seri numarası", "sayaç bilgileri",
            "meter", "electric meter", "serial number"
        ],
        "column_keywords": {
            "seri_no": ["seri numarası", "serial number", "sayaç seri", "meter serial"],
            "guncelleme_zamani": ["güncel", "son güncelleme", "updated", "last updated"],
            "sayac_id": ["sayaç kimliği", "meter id"],
            "marka": ["marka", "brand"],
            "model": ["model"],
        }
    },
    
    "m_load_profile": {
        "table_keywords": [
            "yük profil", "load profile", "yük verileri", "enerji tüketimi",
            "saatlik veri", "hourly data", "profil verileri"
        ],
        "column_keywords": {
            "meter_id": ["sayaç id", "sayaç", "meter", "e_sayac ile ilişkili"],
            "load_profile_date": ["profil tarihi", "zaman", "tarih", "date", "time"],
            "t0": ["toplam enerji", "total energy"],
            "l1_current": ["faz 1 akım", "l1 current", "phase 1"],
            "l1_voltage": ["faz 1 gerilim", "l1 voltage"],
        }
    },
    
    # Diğer önemli tablolar eklenebilir...
    
}
