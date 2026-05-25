# Branch Protection — GitHub UI 설정 가이드

`main` 브랜치 보호는 GitHub Actions YAML 만으로 설정 불가. 저장소 owner 가 1회 GitHub Web UI 에서 설정해야 함. 본 문서는 항목 체크리스트.

## 위치
GitHub 저장소 → **Settings → Branches → Branch protection rules → Add rule**

## 설정 항목

### Branch name pattern
```
main
```

### 보호 옵션 (체크할 것)

- [x] **Require a pull request before merging**
  - Require approvals: **1**
  - Dismiss stale pull request approvals when new commits are pushed (권장)
  - Require review from Code Owners (CODEOWNERS 채운 후)

- [x] **Require status checks to pass before merging**
  - Require branches to be up to date before merging
  - 등록할 status checks (`.github/workflows/ci.yml` 의 job 이름):
    - `python-tests` (Python tests (pytest))
    - `java-tests` (Java unit tests (gradlew))
    - `compose-validate` (docker compose config validation)

- [x] **Require conversation resolution before merging**

- [x] **Do not allow bypassing the above settings**
  - "Allow specified actors to bypass required pull requests" 는 비워둘 것

### 금지 옵션 (체크하지 말 것)

- [ ] Allow force pushes — **비활성**
- [ ] Allow deletions — **비활성**

### Restrict who can push (선택)
- 3명 팀이라 굳이 안 걸어도 되지만, 사고 방지용으로 admin (owner) 만 허용 권장
  - **Restrict who can push to matching branches** → admin 만

## 첫 PR 전 주의
- CI 가 한 번도 실행된 적 없으면 status check 목록에 `python-tests` 등이 나타나지 않는다.
- 임시 브랜치에서 PR 한 번 만들어 CI 가 돌면 status check 등록 가능해진다.
  ```powershell
  git checkout -b chore/ci-bootstrap
  git commit --allow-empty -m "chore: trigger CI for branch protection setup"
  git push -u origin chore/ci-bootstrap
  # GitHub UI 에서 PR 만들고 CI 한 번 돌리고 → branch protection 추가 후 PR 닫기
  ```

## 검증

PR 생성 후 다음이 자동으로 보여야 함:
- `python-tests`, `java-tests`, `compose-validate` 의 상태 (성공/실패)
- 실패 시 "Merge pull request" 버튼 비활성
- approval 0 일 때 머지 차단

## 변경 이력
- 2026-05-20: 초기 작성 (Phase B 협업 인프라 셋업)
