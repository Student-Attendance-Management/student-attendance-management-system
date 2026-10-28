"""Load demo data: python seed.py  (safe to re-run; skips if data exists)."""
import random
from datetime import date, datetime, timedelta
from backend.main import db, init_db, hash_pw

init_db()
con = db()
if con.execute("SELECT 1 FROM students").fetchone():
    print("Data already exists, skipping."); raise SystemExit
random.seed(7)
cl = con.execute("INSERT INTO classes(name,term) VALUES('CSE-A','Sem 5')").lastrowid
subs = [con.execute("INSERT INTO subjects(code,name) VALUES(?,?)", s).lastrowid
        for s in [("UE24CS351A", "Software Engineering"), ("UE24CS352A", "Database Systems"), ("UE24CS353A", "Computer Networks")]]
names = ["Aarav Rao", "Diya Shah", "Rohan Iyer", "Meera Nair", "Kabir Singh", "Ananya Das", "Vikram Joshi", "Sneha Patil"]
sts = []
for n in names:
    e = n.split()[0].lower() + "@student.test"
    i = con.execute("INSERT INTO students(name,email,class_id) VALUES(?,?,?)", (n, e, cl)).lastrowid
    con.execute("INSERT INTO users(username,password_hash,role,ref_id) VALUES(?,?,?,?)", (e, hash_pw("student123"), "Student", i))
    sts.append(i)
facs = []
for n, e in [("Dr. Kulkarni", "kulkarni@faculty.test"), ("Prof. Menon", "menon@faculty.test")]:
    i = con.execute("INSERT INTO faculty(name,email) VALUES(?,?)", (n, e)).lastrowid
    con.execute("INSERT INTO users(username,password_hash,role,ref_id) VALUES(?,?,?,?)", (e, hash_pw("faculty123"), "Faculty", i))
    facs.append(i)
asg = [con.execute("INSERT INTO assignments(faculty_id,subject_id,class_id) VALUES(?,?,?)", (facs[k % 2], subs[k], cl)).lastrowid for k in range(3)]
absent_prone = {sts[2], sts[6]}  # these two end up below 75%
for d in range(14, 0, -1):
    day = date.today() - timedelta(days=d)
    if day.weekday() > 4: continue
    for k, a in enumerate(asg):
        sid = con.execute("INSERT INTO att_sessions(assignment_id,date,period,created_at) VALUES(?,?,?,?)",
                          (a, day.isoformat(), k + 1, datetime.utcnow().isoformat())).lastrowid
        for s in sts:
            p = 0.5 if s in absent_prone else 0.9
            con.execute("INSERT INTO records(session_id,student_id,status,updated_at) VALUES(?,?,?,?)",
                        (sid, s, "Present" if random.random() < p else "Absent", datetime.utcnow().isoformat()))
con.commit()
print("Seeded. Logins: admin/admin123, kulkarni@faculty.test/faculty123, aarav@student.test/student123")
