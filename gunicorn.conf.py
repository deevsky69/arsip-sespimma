# Pengaturan gunicorn (dibaca otomatis dari folder kerja kontainer).
# Log akses mencantumkan header dari reverse proxy agar mudah memeriksa IP asli & HTTPS:
#   <X-Forwarded-For> via <IP proxy> "<request>" <status> <ukuran> <durasi> proto=<X-Forwarded-Proto>
bind = "0.0.0.0:8000"
workers = 3
timeout = 120
accesslog = "-"
access_log_format = '%({x-forwarded-for}i)s via %(h)s "%(r)s" %(s)s %(b)sB %(L)ss proto=%({x-forwarded-proto}i)s'
