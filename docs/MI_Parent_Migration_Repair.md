# Material Instance Parent Repair (OldContents Migration)

## 0) 한 줄 요약
`/Game/Assets/World/...` → `/Game/OldContents/Assets/World/...` 대량 이주 이후, 다수의 `UMaterialInstanceConstant`(MIC)이 **옛 Parent 경로를 그대로 보유**하여 `ParentNotFound`가 발생했습니다.  
`TslMaterialInstanceParentAudit`로 문제를 CSV로 추출하고, `TslMaterialInstanceParentRepair` 커맨드릿으로 **Parent를 새 경로로 재기록(Reparent + Save)** 하여 `ParentNotFound`를 0으로 수렴시켰습니다.

## 목차
- 1) 배경 / 문제 정의
- 2) 원인 추정(가능성이 높은 시나리오)
- 3) 해결 전략 선택
- 4) 구현 산출물(코드)
- 5) 실행 절차(스모크 → 전체 → Repair → 재감사)
- 6) P4V 마무리 체크리스트
- 7) 남은 이슈(ParentNone 105)
- 8) 생성된 아티팩트(파일)
- 9) 커맨드릿 핵심 코드(스니펫) + AnalyzeMaterialInstance 핵심 API 정리
- 10) CSV 컬럼 설명(중간 산출물)
- 11) 이번 작업에서 중요한 Unreal 클래스/시스템 정리

---

## 1) 배경 / 문제 정의

### 1.1 작업 배경
- 이주 대상: `Content/Assets/World` 아래 약 187,719 에셋
- 이주 목적지: `Content/OldContents/Assets` (가상 경로로는 `/Game/OldContents/Assets/...`)

### 1.2 증상
- 일부(대량)의 `Material Instance`에서 `Parent` 참조가 깨져, 에디터/런타임에서 머티리얼이 정상 렌더링되지 않거나 로드 경고가 발생.

### 1.3 핵심 관찰(스캔 결과로 확인된 사실)
Audit 결과(`broken_assets_list.csv`)는 다음과 같은 분포였습니다:
- Broken 총 **12,997**
  - `ParentNotFound` **12,892 (99.2%)**
  - `ParentNone` **105 (0.8%)**
- `ParentNotFound`의 `Parent_ParsedObjectPath`는 전부 **`/Game/Assets/World/...`** prefix
- `RedirectorHops=0` (즉, old parent 경로에 redirector 체인이 잡히지 않음)
- 고유 old parent 경로 수가 **92개**로 매우 작음 → “부모 몇십 개”가 병목/원인점으로 수렴

---

## 2) 원인 추정(가능성이 높은 시나리오)

### 2.1 왜 `/Game/Assets/World/...`를 기억하는가?
UE의 참조는 “파일 시스템 경로”가 아니라, **패키지/오브젝트 경로(`/Game/.../Asset.Asset`)** 를 기반으로 저장됩니다.  
따라서 폴더 이동/리네임 이후에도 **참조가 자동으로 재기록되지 않으면** 여전히 옛 경로를 바라봅니다.

### 2.2 Redirector와의 관계
에디터에서 “Move/Rename”를 정상 수행하면 보통 old 위치에 `UObjectRedirector`가 남습니다.
- redirector는 `DestinationObject` 태그로 새 경로를 가리킵니다.
- 이후 “Fix Up Redirectors”를 수행하면 참조들이 새 경로로 재기록되고, redirector는 제거됩니다.

이번 케이스는 `RedirectorHops=0` 이었기 때문에,
- old parent 위치에 redirector가 남아 있지 않거나
- 참조 재기록(Fixup)이 일부 패키지에 적용되지 않았거나
- (또는) 이주 과정이 에디터의 rename/move 파이프라인을 우회했을 가능성
등을 강하게 시사합니다.

---

## 3) 해결 전략 선택

### 3.1 후보
1) redirector를 재생성/복구 후, fixup을 다시 수행  
2) **MIC의 Parent를 새 경로로 직접 재기록(Reparent + Save)** ← 이번에 선택한 근본 해결  
3) 런타임에서 임시 매핑/패치(비추천: 근본 해결 아님)

### 3.2 왜 “Reparent + Save”를 선택했는가?
- `ParentNotFound`가 12,892개로 대량이지만, 고유 parent 경로가 92개뿐이라 **매핑 검증 비용이 작음**
- 오탐 방지를 위해 parent를 사람이 검토 가능한 `parent_map.csv`로 분리(2-pass)
- 성공 시, redirector 의존 없이 **데이터 자체가 정상화**되어 추후 유지보수에 유리

---

## 4) 구현 산출물(코드)

### 4.1 신규 커맨드릿: `TslMaterialInstanceParentRepair`
- 파일:
  - `Tsl/Source/TslEditor/Private/Commandlet/TslMaterialInstanceParentRepairCommandlet.h`
  - `Tsl/Source/TslEditor/Private/Commandlet/TslMaterialInstanceParentRepairCommandlet.cpp`
- 기본값: `DryRun` (저장 안 함) → `-Apply`에서만 실제 저장

### 4.2 주요 설계 포인트

#### (A) 2-pass 구조(안전/검토 가능)
- **Pass1 (ParentMap 생성)**  
  Audit CSV에서 old parent를 모아 remap 규칙 적용 후, AssetRegistry로 존재/타입 검증 → `parent_map.csv` 생성  
  - remap 실패 시 fallback 검색은 “후보가 1개일 때만” 자동 채택  
  - 후보가 여러 개면 `Ambiguous`로 남기고 자동 선택 금지
- **Pass2 (MI reparent + save)**  
  각 MI를 로드하여 `SetParentEditorOnly(NewParent)` 후 `SavePackage`

#### (B) 안전성(크래시/손상 에셋 방어)
- Windows에서 `LoadObject`를 SEH 가드로 감싼 `LoadObjectGuarded` 사용
- 로드 실패는 `UE::AssetLoadFailureLog::RecordFailure`로 기록

#### (C) 성능/메모리(대량 처리)
- parent는 최대 92개 수준이므로 캐싱(중복 로드 감소)
- MI는 배치 단위로 언로드/GC:
  - `UPackageTools::UnloadPackages(...)` + `CollectGarbage(...)`
  - parent 패키지는 GC/언로드 대상에서 제외(캐시 안정성)
- CSV 출력은 버퍼링 후 일정 크기에서 flush

#### (D) Perforce read-only 대응
- `-nop4` 환경에서 저장 시 read-only로 실패할 수 있음
- `-MakeWritable`는 파일 속성을 writable로 변경 후 저장(오프라인 수정)  
  → 이후 P4V에서 `Reconcile Offline Work` 필요

---

## 5) 실행 절차 (이번 작업에서 실제로 수행한 순서)

### 5.1 에디터 빌드(컴파일 검증)
레포 표준 방식에 맞춰 `2_build_editor.bat` 기반으로 에디터 타겟 빌드로 컴파일 깨짐 여부를 확인했습니다.

### 5.2 Audit 실행(스모크 → 전체)
스모크는 “짧은 루트 1개로 빠른 검증”, 전체는 “문제 규모 파악/리포트 생성” 목적입니다.

예시:
```bat
UnrealEditor-Cmd.exe TslGame.uproject -run=TslMaterialInstanceParentAudit ^
  -Root=/Game/OldContents/Assets/World_Desert ^
  -Csv=E:/Tsl/Tsl/Saved/Migration_Report/broken_assets_list_smoke.csv ^
  -VerifyLoad=BrokenOnly -unattended -nop4 -nosplash -stdout -FullStdOutLogOutput
```

```bat
UnrealEditor-Cmd.exe TslGame.uproject -run=TslMaterialInstanceParentAudit ^
  -Root=/Game/OldContents/Assets ^
  -Csv=E:/Tsl/Tsl/Saved/Migration_Report/broken_assets_list.csv ^
  -VerifyLoad=BrokenOnly -unattended -nop4 -nosplash -stdout -FullStdOutLogOutput
```

### 5.3 Audit CSV 분석 결과(수치)
- `broken_assets_list.csv`:
  - `ParentNotFound` 12,892
  - `ParentNone` 105
  - 고유 old parent 92
  - `RedirectorHops=0` (ParentNotFound 전부)

### 5.4 Repair 실행(드라이런 → 적용)
CSV가 Excel 등으로 열려있으면 공유 위반으로 읽기 실패할 수 있어, 필요 시 복사본을 사용했습니다.

#### (1) DryRun(저장 없음)
```bat
UnrealEditor-Cmd.exe TslGame.uproject -run=TslMaterialInstanceParentRepair ^
  -CsvIn=E:/Tsl/Tsl/Saved/Migration_Report/broken_assets_list_copy.csv ^
  -CsvOut=E:/Tsl/Tsl/Saved/Migration_Report/mi_parent_repair_dryrun.csv ^
  -ParentMapOut=E:/Tsl/Tsl/Saved/Migration_Report/parent_map.csv ^
  -DryRun -unattended -nop4 -nosplash -stdout -FullStdOutLogOutput
```

검증 포인트:
- ParentMap: `Ok=92 Ambiguous=0 Failed=0`

#### (2) Apply(저장) - read-only로 실패한 1차 시도
```bat
UnrealEditor-Cmd.exe TslGame.uproject -run=TslMaterialInstanceParentRepair ^
  -CsvIn=E:/Tsl/Tsl/Saved/Migration_Report/broken_assets_list_copy.csv ^
  -CsvOut=E:/Tsl/Tsl/Saved/Migration_Report/mi_parent_repair_apply.csv ^
  -ParentMapIn=E:/Tsl/Tsl/Saved/Migration_Report/parent_map.csv ^
  -ParentMapOut=E:/Tsl/Tsl/Saved/Migration_Report/parent_map.csv ^
  -Apply -unattended -nop4 -nosplash -stdout -FullStdOutLogOutput
```

결과:
- `Failed_SaveReadOnly` 12,892

#### (3) Apply(저장) - `-MakeWritable`로 성공
```bat
UnrealEditor-Cmd.exe TslGame.uproject -run=TslMaterialInstanceParentRepair ^
  -CsvIn=E:/Tsl/Tsl/Saved/Migration_Report/broken_assets_list_copy.csv ^
  -CsvOut=E:/Tsl/Tsl/Saved/Migration_Report/mi_parent_repair_apply_writable.csv ^
  -ParentMapIn=E:/Tsl/Tsl/Saved/Migration_Report/parent_map.csv ^
  -ParentMapOut=E:/Tsl/Tsl/Saved/Migration_Report/parent_map.csv ^
  -Apply -MakeWritable -unattended -nop4 -nosplash -stdout -FullStdOutLogOutput
```

`mi_parent_repair_apply_writable.csv` 집계:
- `Applied_Reparented` 12,892 (SaveSuccess=True)
- `Skipped_ParentNone` 105

### 5.5 Repair 후 Audit 재실행(검증)
```bat
UnrealEditor-Cmd.exe TslGame.uproject -run=TslMaterialInstanceParentAudit ^
  -Root=/Game/OldContents/Assets ^
  -Csv=E:/Tsl/Tsl/Saved/Migration_Report/broken_assets_list_after_repair.csv ^
  -VerifyLoad=BrokenOnly -unattended -nop4 -nosplash -stdout -FullStdOutLogOutput
```

결과:
- Broken 105 (전부 `ParentNone`)

---

## 6) P4V 마무리 체크리스트(중요)
이번 적용은 `-nop4` + `-MakeWritable`로 **체크아웃 없이 로컬 uasset을 저장**한 형태입니다. 따라서:
- P4V에서 `Reconcile Offline Work...`로 변경된 `*.uasset`을 **Open for edit** 상태로 반영
- 체인지리스트에 `Saved/` 아래 CSV/MD는 보통 submit 대상이 아님(팀 정책 따르기)
- submit 후 클린 워크스페이스에서 sync → Audit 재실행으로 재현성 확인 권장

---

## 7) 남은 이슈: `ParentNone` 105개
`ParentNone`은 “Parent 정보가 없거나(진짜 None), Audit 단계에서 Parent 태그 파싱 불가”인 케이스입니다.
- 자동 복구는 오탐 위험이 커서 기본 정책으로는 스킵
- 처리 방향:
  - 수동: 에디터에서 MIC 열어서 Parent 지정 후 저장
  - 보조: `-SuggestParentForNone`로 후보 제안 리포트(현재는 네이밍 기반, 후보 1개일 때만 힌트)

---

## 8) 생성된 아티팩트(파일)
- Audit(이전): `Tsl/Saved/Migration_Report/broken_assets_list.csv`
- Audit(스모크): `Tsl/Saved/Migration_Report/broken_assets_list_smoke.csv`
- Audit(잠금 회피용 복사본): `Tsl/Saved/Migration_Report/broken_assets_list_copy.csv`
- ParentMap: `Tsl/Saved/Migration_Report/parent_map.csv` (92 rows, Ok=92)
- Repair 결과:
  - DryRun: `Tsl/Saved/Migration_Report/mi_parent_repair_dryrun.csv`
  - Apply(실패: read-only): `Tsl/Saved/Migration_Report/mi_parent_repair_apply.csv`
  - Apply(성공: -MakeWritable): `Tsl/Saved/Migration_Report/mi_parent_repair_apply_writable.csv`
- Audit(이후): `Tsl/Saved/Migration_Report/broken_assets_list_after_repair.csv` (ParentNone 105)

---

## 9) 커맨드릿 핵심 코드(스니펫)
아래는 “이 문제를 어떻게 탐지/복구하는지”를 이해하기 위한 핵심 코드 조각입니다.
- Audit: `Tsl/Source/TslEditor/Private/Commandlet/TslMaterialInstanceParentAuditCommandlet.cpp`
- Repair: `Tsl/Source/TslEditor/Private/Commandlet/TslMaterialInstanceParentRepairCommandlet.cpp`

### 9.1 크래시 방지 로드(손상 에셋 방어): `LoadObjectGuarded`
Windows에서 손상된 `.uasset`를 로드하다가 Access Violation이 나더라도 프로세스가 죽지 않도록 SEH로 감쌉니다.
```cpp
	static UObject* LoadObjectGuarded(const FString& ObjectPath, ELoadFlags LoadFlags, const FLinkerInstancingContext* InstancingContext, bool& bOutHadException)
{
	bOutHadException = false;

#if PLATFORM_WINDOWS && !PLATFORM_SEH_EXCEPTIONS_DISABLED
	if (IsSafeAssetLoadEnabled())
	{
		__try
		{
			return LoadObject<UObject>(nullptr, *ObjectPath, nullptr, LoadFlags, nullptr, InstancingContext);
		}
		__except (EXCEPTION_EXECUTE_HANDLER)
		{
			bOutHadException = true;
			return nullptr;
		}
	}
#endif

	return LoadObject<UObject>(nullptr, *ObjectPath, nullptr, LoadFlags, nullptr, InstancingContext);
	}
```

### 9.2 Redirector 체인 해석(레지스트리 기반): `ResolveRedirectorChain`
redirector를 직접 로드하지 않고 **AssetRegistry 메타데이터**(class + `DestinationObject` 태그)만으로 목적지를 따라갑니다.
```cpp
const FAssetData CurrentAssetData = AssetRegistry.GetAssetByObjectPath(CurrentPath);
if (!CurrentAssetData.IsValid())
{
	// redirector를 밟은 뒤 목적지가 없으면 “깨진 체인”으로 명확히 마킹
	if (Result.bHadRedirector)
	{
		Result.bIsBroken = true;
		Result.FailureReason = TEXT("RedirectorDestinationNotFound");
	}
	return Result;
}

if (CurrentAssetData.AssetClassPath != UObjectRedirector::StaticClass()->GetClassPathName())
{
	Result.FinalObjectPath = CurrentPath;
	return Result;
}

FString DestinationObjectPathString;
if (!CurrentAssetData.GetTagValue(FName(TEXT("DestinationObject")), DestinationObjectPathString))
{
	Result.bIsBroken = true;
	Result.FailureReason = TEXT("RedirectorMissingDestinationTag");
	return Result;
}
```

### 9.3 Audit의 핵심 판정 흐름(요약): Parent 태그 → 파싱 → redirector → 존재/타입 검증
Audit은 “레지스트리만으로 빠르게 판정(기본)”하고, 필요 시 `-VerifyLoad`로 로드 검증을 추가합니다.
```cpp
// (개념 요약) AnalyzeMaterialInstance()
// 1) Parent 태그 확인
// 2) Parent_TagValue 파싱 → Parent_ParsedObjectPath
// 3) redirector 체인 해석 → Parent_ResolvedObjectPath / RedirectorHops
// 4) 레지스트리에서 Parent 존재/타입 검증 → Issue 결정

if (!bHasParentTag)                        Issue = "MissingParentTag";
else if (ParentTagValue.IsEmpty())         Issue = "EmptyParentTag";
else if (ParentTagValue == "None")         Issue = "ParentNone";
else if (!TryParseObjectPath(...))         Issue = "InvalidParentTagValue";
else if (ResolveResult.bIsBroken)          Issue = "BrokenRedirectorChain"; Notes = ResolveResult.FailureReason;
else if (!AR.HasAsset(ParsedParentPath))   Issue = "ParentNotFound";
else if (!AR.HasAsset(ResolvedParentPath)) Issue = "ResolvedParentNotFound";
else if (!IsMaterialInterface(Resolved))   Issue = "ResolvedParentWrongType";
else                                       Issue = ""; // 정상
```

#### 9.3.1 `AnalyzeMaterialInstance()`에서 사용된 핵심 함수/프로퍼티 정리
Audit CSV(`broken_assets_list*.csv`)의 각 컬럼은, 아래 API/프로퍼티에서 직접 파생됩니다.

**입력/출력 구조**
- 입력(핵심): `FAssetData MiAssetData`, `IAssetRegistry& AssetRegistry`, `Options.VerifyLoadMode`, `Options.MaxRedirectorHops`
- 출력(핵심): `FReportRow OutRow`(= CSV 컬럼 묶음), `InOutLoadedPackagesForUnload`(VerifyLoad에서 로드된 패키지 언로드용)

**레지스트리 기반(기본 모드, 빠름)**
- `MiAssetData.GetObjectPathString()` → `MI_ObjectPath`
- `MiAssetData.PackageName` / `MiAssetData.AssetClassPath` → `MI_PackageName`, `MI_AssetClass`
- `MiAssetData.GetTagValue("Parent", ParentTagValue)` → `Parent_TagValue`
- `TryParseObjectPath(Parent_TagValue)` → `Parent_ParsedObjectPath` (실패 시 `InvalidParentTagValue`)
- `ResolveRedirectorChain(AssetRegistry, ParsedParentPath, Options.MaxRedirectorHops)`  
  → `Parent_ResolvedObjectPath`, `RedirectorHops`, (깨진 체인 시 `Issue=BrokenRedirectorChain`, `Notes=FailureReason`)
- `AssetRegistry.GetAssetByObjectPath(Path, /*bIncludeOnlyOnDiskAssets=*/true)`  
  → parent 존재 여부 판정(`ParentNotFound` / `ResolvedParentNotFound`) 및  
  `Parent_ResolvedClass`, `Parent_ResolvedPackageName` 채우기
- `ValidParentClassPaths.Contains(ResolvedParentAssetData.AssetClassPath)`  
  → 타입 검증(`Issue=ResolvedParentWrongType`)
- `FPackageName::TryConvertLongPackageNameToFilename(...)`  
  → `MI_FilePath`, `Parent_ResolvedFilePath`

**VerifyLoad 기반(옵션: `-VerifyLoad=BrokenOnly|All`, 느림)**
- 목적: “레지스트리 오탐(false positive) 제거” + “로드 기준의 mismatch/타입 이상 리포트”
- `FindPackage(nullptr, *MI_PackageName)` + `LoadedObject->GetOutermost()`  
  → “이번 VerifyLoad에서 새로 로드된 패키지”만 `InOutLoadedPackagesForUnload`에 넣어, 배치 언로드/GC로 메모리를 회수
- `LoadObjectGuarded(MI_ObjectPath)`  
  → 로드 실패 시 `Issue=MiLoadFailed`, `Notes+=MI_LoadFailed` + `AssetLoadFailureLog` 기록
- `Cast<UMaterialInstance>(LoadedObject)`  
  → 실패 시 `Issue=MiLoadedWrongType`, `Notes+=MI_LoadedNonMI`
- `UMaterialInstance::Parent` (핵심 프로퍼티)  
  - `nullptr`이면 `Issue=ParentNone`, `Notes+=MI_LoadedParentNone`
  - `!Parent->IsA(UMaterialInterface)`이면 `Issue=LoadedParentWrongType`
- `GetPathNameSafe(LoadedMi->Parent)` + `FSoftObjectPath(...).GetWithoutSubPath()`  
  → 로드된 parent 경로를 정규화(서브오브젝트 제거)
- 비교 로직(중요):
  - `LoadedParentPath == (RegistryResolved 또는 RegistryParsed)`이면 → 기존 `Issue`를 **지움**(레지스트리 stale로 인한 오탐 제거)
  - 불일치면 → `Issue=ParentMismatch_LoadVsRegistry`로 남기고 `Notes`에 `LoadedParent=...;RegistryResolved/RegistryParsed=...` 기록

### 9.4 Repair의 핵심(2-pass): ParentMap 생성 → MI Reparent + Save
**Pass1(ParentMap)**: old parent(최대 92개)를 remap/검증해 사람이 확인 가능한 `parent_map.csv`를 생성합니다.  
**Pass2(Apply)**: MI를 로드해 `SetParentEditorOnly`로 parent를 재기록하고 패키지를 저장합니다.
```cpp
// Pass1(핵심): OldParent → NewParent 후보 산출 + 레지스트리 검증
const FString* OverrideNewParent = ParentMapOverrides.Find(OldParentObjectPath);
if (OverrideNewParent)
{
	Entry.CandidateObjectPath = *OverrideNewParent; // 사람이 지정한 값은 최우선
	Entry.Notes = TEXT("Source=ParentMapIn");
}
else
{
	Entry.CandidateObjectPath = ApplyRemapRules(Options.RemapRules, OldParentObjectPath); // prefix remap
	Entry.Notes = TEXT("Source=Remap");
}

// redirector 체인 + 타입(MaterialInterface 계열) 검증을 로드 없이 수행
if (TryResolveParentByObjectPath(AssetRegistry, ValidParentClassPaths, Entry.CandidateObjectPath, ...))
{
	Entry.Status = TEXT("Ok");
}
else
{
	// 안전 정책: override가 invalid이면 fallback으로 덮어쓰지 않음(사람 의도를 존중)
	// remap 실패 시에만 fallback(이름 기반)을 고려하고, 후보가 1개일 때만 자동 채택
}

// Pass2(핵심): 이미 올바르면 저장하지 않고(멱등성), -Apply에서만 실제 저장
LoadedMi->Modify();
LoadedMi->SetParentEditorOnly(NewParent);
LoadedMi->PostEditChange();
LoadedMi->MarkPackageDirty();

FSavePackageArgs SaveArgs;
SaveArgs.TopLevelFlags = RF_Public | RF_Standalone;
SaveArgs.Error = GError;
SaveArgs.SaveFlags = SAVE_NoError;

const bool bSaved = UPackage::SavePackage(PackageToSave, nullptr, *PackageFilename, SaveArgs);
```
추가로, 대량 실행에서 메모리 누수를 피하기 위해 `UPackageTools::UnloadPackages + CollectGarbage`를 배치로 수행하며,  
캐시된 Parent는 `TStrongObjectPtr`로 잡아 GC 이후에도 dangling pointer가 되지 않도록 방어합니다.

---

## 10) CSV 컬럼 설명(중간 산출물)
이번 작업에서 중요한 CSV는 3종입니다.
- Audit 결과: `broken_assets_list*.csv` (문제 “발견/진단”)
- ParentMap: `parent_map.csv` (old parent → new parent 매핑 “검증/검토”)
- Repair 결과: `mi_parent_repair_*.csv` (실제 “변경/저장 결과”)

### 10.1 Audit 결과 CSV: `broken_assets_list*.csv`
헤더:
```
"Issue","MI_ObjectPath","MI_PackageName","MI_AssetClass","MI_FilePath","Parent_TagValue","Parent_ParsedObjectPath","Parent_ResolvedObjectPath","Parent_ResolvedClass","Parent_ResolvedPackageName","Parent_ResolvedFilePath","RedirectorHops","Notes"
```

| 컬럼 | 의미 | 어디서 얻는가(대략) |
|---|---|---|
| `Issue` | 진단 결과 코드(비정상이면 문자열, 정상이면 비어있을 수 있음) | `AnalyzeMaterialInstance()`에서 규칙 기반 결정(일부는 `-VerifyLoad`로 갱신/추가) |
| `MI_ObjectPath` | 검사 대상 MIC의 오브젝트 경로(`/Game/.../MI_X.MI_X`) | AssetRegistry `FAssetData::GetObjectPathString()` |
| `MI_PackageName` | MI 패키지 이름(`/Game/.../MI_X`) | AssetRegistry `FAssetData::PackageName` |
| `MI_AssetClass` | MI의 클래스 경로(대개 `MaterialInstanceConstant`) | AssetRegistry `FAssetData::AssetClassPath` |
| `MI_FilePath` | MI `.uasset` 파일 경로 | `FPackageName::TryConvertLongPackageNameToFilename()` |
| `Parent_TagValue` | AssetRegistry에 기록된 Parent 태그 원문(ExportText 형태 또는 `None`) | `FAssetData::GetTagValue("Parent")` |
| `Parent_ParsedObjectPath` | `Parent_TagValue`를 `/Game/.../Asset.Asset`로 파싱한 값 | `TryParseObjectPath()` |
| `Parent_ResolvedObjectPath` | redirector 체인을 따라간 최종 목적지(또는 입력 그대로) | `ResolveRedirectorChain()` |
| `Parent_ResolvedClass` | 최종 parent의 클래스(레지스트리 기준) | `ResolvedParentAssetData.AssetClassPath` |
| `Parent_ResolvedPackageName` | 최종 parent의 패키지 이름 | `ResolvedParentAssetData.PackageName` |
| `Parent_ResolvedFilePath` | 최종 parent 파일 경로 | package name → filename 변환 |
| `RedirectorHops` | redirector hop 수(0이면 redirector 없음) | `ResolveRedirectorChain().HopCount` |
| `Notes` | 추가 진단(redirector 실패 사유, VerifyLoad 결과, mismatch 경로 등) | Audit 내부에서 누적 문자열로 기록 |

**자주 나오는 Issue 값(의미)**  
이슈 문자열은 “정확히 어떤 케이스로 깨졌는지”를 구분하기 위한 코드입니다.
- `ParentNone`: 레지스트리 상 Parent가 `None`
- `ParentNotFound`: `Parent_ParsedObjectPath`가 레지스트리에 없음(옛 경로를 가리키는 전형적인 케이스)
- `BrokenRedirectorChain`: redirector 체인 자체가 깨짐(루프/목적지 태그 없음/목적지 미존재 등). 세부 사유는 `Notes`에 기록
- `ResolvedParentWrongType`: 목적지는 있으나 `MaterialInterface` 계열이 아님
- `ParentMismatch_LoadVsRegistry`: `-VerifyLoad` 시 “실제 로드된 Parent”와 “레지스트리 해석 Parent”가 불일치

### 10.2 ParentMap CSV: `parent_map.csv`
헤더:
```
"OldParentObjectPath","SuggestedNewParentObjectPath","ResolvedNewParentObjectPath","ResolvedClass","Status","Notes"
```

| 컬럼 | 의미 |
|---|---|
| `OldParentObjectPath` | Audit에서 수집한 old parent 경로(고유 92개) |
| `SuggestedNewParentObjectPath` | remap/오버라이드/fallback으로 제안된 new parent “후보” |
| `ResolvedNewParentObjectPath` | 후보가 redirector라면 체인을 따라간 최종 목적지(실제 적용 대상) |
| `ResolvedClass` | 최종 목적지의 클래스(레지스트리 기준) |
| `Status` | 매핑 결과 상태(`Ok`, `Ambiguous_Fallback`, `OverrideInvalid` 등) |
| `Notes` | Source/Reason/Fallback 후보 수 등 추가 정보 |

**사람이 개입하는 지점(의도)**  
`parent_map.csv`는 “자동 선택이 위험한 상황(동명이인/복수 후보)”에서 사람이 92개만 빠르게 검토하도록 만든 안전장치입니다.  
`-ParentMapIn`으로 재입력할 때는 `NewParentObjectPath` 컬럼이 있으면 우선 사용하며, 없으면 `SuggestedNewParentObjectPath`를 사용합니다.

### 10.3 Repair 결과 CSV: `mi_parent_repair_*.csv`
헤더:
```
"Issue","MI_ObjectPath","MI_PackageName","MI_FilePath","OldParent_ObjectPath","NewParent_CandidateObjectPath","NewParent_ResolvedObjectPath","NewParent_Class","Action","SaveSuccess","Notes"
```

| 컬럼 | 의미 |
|---|---|
| `Issue` | 입력 Audit 행의 Issue(기본적으로 그대로 복사) |
| `MI_ObjectPath` | 대상 MI 오브젝트 경로 |
| `MI_PackageName` | 대상 MI 패키지 |
| `MI_FilePath` | 대상 MI 파일 경로 |
| `OldParent_ObjectPath` | old parent(ParentNotFound에서만 의미 있음) |
| `NewParent_CandidateObjectPath` | remap/override/fallback로 선택된 후보 |
| `NewParent_ResolvedObjectPath` | redirector 체인 해석 후 최종 parent(실제 로드/적용) |
| `NewParent_Class` | 최종 parent의 클래스(레지스트리 기준) |
| `Action` | 커맨드릿이 한 행동(예: `DryRun_WouldReparent`, `Applied_Reparented`, `Failed_SaveReadOnly`) |
| `SaveSuccess` | 저장 성공 여부(`True/False`) |
| `Notes` | CurrentParent, ClearedReadOnly, 실패 사유 등 추가 정보 |

**이번 실행에서의 대표 Action 값**
- `Applied_Reparented`: Parent 재기록 + 저장 성공
- `Failed_SaveReadOnly`: 파일이 read-only라 저장 실패(1차 Apply 시도에서 발생)
- `Skipped_ParentNone`: Parent 정보가 없어 자동 적용을 스킵(105개)

---

## 11) 이번 작업에서 중요한 Unreal 클래스/시스템 정리
“무엇을 왜 썼는지”를 중심으로, Audit/Repair 코드에서 핵심이 되는 엔진 타입을 요약합니다.

### 11.1 Commandlet / 실행 맥락
- `UCommandlet`  
  에디터/툴 환경에서 커맨드라인으로 실행되는 작업 단위입니다. 이번 작업은 “대량 스캔/대량 저장”이 목적이라, UI 없이 배치로 돌리기 좋은 Commandlet 형태가 적합했습니다.

### 11.2 머티리얼 계층
- `UMaterialInterface`  
  `UMaterial`/`UMaterialInstance` 계열의 공통 베이스입니다. “Parent가 유효한지”를 타입 레벨에서 검증하기 위해, AssetRegistry 기반으로 “MaterialInterface 계열인지” 확인하는 기준으로 사용했습니다.
- `UMaterialInstanceConstant`  
  우리가 실제로 수정하는 대상(MI) 타입입니다. Repair에서 `SetParentEditorOnly(NewParent)`로 Parent를 재지정하고, 패키지를 저장하여 참조를 데이터에 재기록합니다.

### 11.3 Asset Registry (대량 처리 핵심)
- `FAssetRegistryModule` / `IAssetRegistry`  
  온디스크 자산의 메타데이터를 쿼리하는 시스템입니다. 19만 규모에서 전체 에셋을 UObject로 로드하면 OOM/프리즈 위험이 크기 때문에, **존재/클래스/태그** 등은 최대한 AssetRegistry로 해결했습니다.
- `FAssetData`  
  개별 에셋의 “레지스트리 레코드”입니다. `AssetClassPath`, `PackageName`, `GetTagValue()`(예: `Parent`, redirector의 `DestinationObject`) 등을 통해 로드 없이 판정/진단/경로 변환을 수행합니다.

### 11.4 Redirector 체인(경로 이동의 흔적)
- `UObjectRedirector`  
  에디터에서 Move/Rename 시 구 경로에 남아 옛 참조를 새 경로로 연결해주는 오브젝트입니다. 이번 작업에서는 redirector를 직접 로드하기보다, AssetRegistry의 class/태그만으로 체인을 따라가기 위해 `ResolveRedirectorChain()`에서 타입 비교 대상으로 사용했습니다.

### 11.5 경로/참조 표현
- `FSoftObjectPath`  
  `/Game/.../Asset.Asset` 형태의 오브젝트 경로를 안전하게 다루는 타입입니다. Audit/Repair 모두 “Parent 태그 문자열”을 파싱해 정규화하고 비교하기 위해 사용했습니다.
- `FPackageName`  
  LongPackageName(`/Game/...`) ↔ 파일경로(`.../Content/...uasset`) 변환 유틸입니다. CSV에 사람이 확인 가능한 `MI_FilePath`/`Parent_ResolvedFilePath`를 기록하기 위해 사용했습니다.

### 11.6 로드/저장/메모리 관리(대량 적용 핵심)
- `LoadObject`  
  실제 수정(Repair) 단계에서는 MI와 Parent를 UObject로 로드해야 합니다. 손상 에셋로 인한 크래시를 완화하기 위해 Windows에서는 SEH로 감싼 `LoadObjectGuarded()`를 사용했습니다.
- `UE::AssetLoadFailureLog`  
  로드 실패를 누적 기록하는 엔진 로깅 유틸입니다. “어떤 에셋이 로드에서 죽는지/깨졌는지”를 추적할 수 있어 대량 처리에서 중요합니다.
- `UPackage` / `UPackage::SavePackage` / `FSavePackageArgs`  
  MIC의 변경을 디스크에 반영하는 저장 경로입니다. `FSavePackageArgs`를 커맨드릿 친화적으로 설정하여, 대량 저장 시 로그 폭주/부작용을 최소화했습니다.
- `UPackageTools::UnloadPackages` (+ `CollectGarbage`)  
  많은 MI를 순회하면서 계속 로드하면 메모리가 누적됩니다. 일정 배치마다 언로드 + GC를 수행해 OOM/프리즈를 방지했습니다.
- `TStrongObjectPtr`  
  parent 캐시를 GC로부터 안전하게 유지하기 위한 강한 참조입니다. 배치 언로드/GC 이후에도 캐시된 Parent 포인터가 무효화되지 않도록 방어합니다.

### 11.7 CSV 파싱/출력(대량 로그)
- `FCsvParser`  
  Audit/Repair 모두 CSV를 읽고 쓰는 도구입니다. Repair는 Audit CSV를 입력으로 받아 “정확히 그 목록만” 처리하도록 구성했습니다(안전성/성능).
