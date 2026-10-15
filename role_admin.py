"""Operator-only role management. Use from the STRATO API container.

Example:
  docker compose exec api python /app/role_admin.py your_existing_username admin
This runs inside the container and requires direct server access; no public
registration field can grant elevated privileges.
"""
import sys
import platform_api

def main():
    if len(sys.argv)!=3 or sys.argv[2] not in ("admin","tester","member"):
        raise SystemExit("Usage: python role_admin.py <existing-username> <admin|tester|member>")
    username=sys.argv[1].lower()
    role=sys.argv[2]
    with platform_api.connection() as c:
        user=c.execute("SELECT id,role FROM rf_users WHERE username=?",(username,)).fetchone()
        if not user:
            raise SystemExit("Unknown username: "+username)
        c.execute("UPDATE rf_users SET role=? WHERE id=?",(role,user["id"]))
    print("Role updated for",username,"to",role)

if __name__=="__main__":
    main()
