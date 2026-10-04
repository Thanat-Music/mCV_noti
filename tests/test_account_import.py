import sqlite3
import pytest
from scripts.import_account import import_account


def test_import_idempotent_and_preserves_existing_state(tmp_path):
    source = tmp_path / "old.db"
    target = tmp_path / "new.db"
    db = sqlite3.connect(source)
    db.execute("CREATE TABLE user(user_id TEXT,cname TEXT,cpass TEXT,Line_uid TEXT)")
    db.execute("INSERT INTO user VALUES('u1','cipher-name','cipher-pass','recipient')")
    db.commit()
    db.close()
    import_account(source, target)
    import_account(source, target)
    db = sqlite3.connect(target)
    assert db.execute("SELECT COUNT(*) FROM user").fetchone() == (1,)
    db.execute("UPDATE user SET cpass='changed'")
    db.commit()
    with pytest.raises(RuntimeError):
        import_account(source, target)
    assert db.execute("SELECT cpass FROM user").fetchone() == ("changed",)
    db.close()
