# Guvenlik Politikasi

## Desteklenen Surumler

| Surum | Destek |
|-------|--------|
| 2.x   | Aktif destek |
| 1.x   | Guvenlik yamalari |
| < 1.0 | Desteklenmiyor |

## Guvenlik Acigi Raporlama

Guvenlik acigi buldunuz mu? Lutfen **acik bir issue ACMAYIN**.

### Raporlama Adimi

1. Acigi detayli sekilde aciklayin
2. Mumkunse yeniden uretme adimlari ekleyin
3. Etkilenen surumleri belirtin
4. GitHub Security Advisories uzerinden raporlayin

### Beklentiler

- 48 saat icinde ilk yanit
- 7 gun icinde duzeltme plani
- Duzeltme yayinlaninca kredi verilir

### Kapsam

- Nazar'in kendisindeki guvenlik aciklari
- Tarama sirasinda bilgi sizintisi
- Dependency chain aciklari

### Kapsam Disi

- Nazar'in taradigi projelerdeki aciklar (bu zaten Nazar'in isi)
- Sosyal muhendislik
- DoS saldirilari

## Bilinen Guvenlik Onlemleri

- Nazar tarama sirasinda hicbir dosyayi degistirmez
- Ag istekleri sadece API test asamasinda yapilir
- Tum dosya islemleri read-only'dir
- Secret pattern'leri raporda maskelenir
