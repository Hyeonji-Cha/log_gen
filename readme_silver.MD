# 개요
- Bronze (raw 데이터 저장, 모은 단위 중요)
  - log generator => kinesis => firehose(1Mib/60s) => s3 bronze (raw data, GZIP)
- Silver (raw 데이터 -> 정제/전처리등 데이터 조작 -> 저장)
  - Streamming Ingestion => `Streamming Processing + Medalion Architecture`
  - step 1
    - log generator => kinesis(input) => flink(자바,파이썬(pyflink), pom.xml,maven) => kinesis(outut) => firehose => s3 silver
      - `flink, kinesis(outut), firehose 3개 리소스` 생성
      - s3 silver : 기존 버킷 하위에 구성
        - jsonl 저장 -> GZIP 저장
        - parquet 저장 -> Glue 스키마 구성하여 연동 
  - step 2
    - log generator => kinesis(input) => lambda => kinesis(outut) => firehose => s3 silver

# Flink
- 실시간으로 스트리밍 데이터에서 실행 가능한 분석 정보를 확보
  - 실시간 데이터를 실시간으로 전처리/정제등 작업 가능 -> 거의 지연 없다
- 실시간일 필요 없다 => Airlfow or Step Function(AWS) 이용하여 Batch Processing 처리
- Siiver 단계로 저장하는 방법
  - [v]실시간 -> flink, lambda
  - 배치   -> Airlfow or Step Function(AWS)

- 특징
  - 실시간 스트림 처리: Kinesis에서 들어오는 데이터를 계속 읽으면서 즉시 처리
  - Stateful Processing: 이전 이벤트 상태를 기억하면서 집계·판단 가능
  - Event Time 지원: 데이터가 실제 발생한 시간을 기준으로 처리 가능
  - Window 처리: 1분, 5분, 1시간 단위 집계 같은 작업에 강함
  - Checkpoint / 장애 복구: 처리 상태를 저장해서 장애 후 이어서 처리 가능
  - Exactly-once 처리 지원: 중복이나 누락을 최소화하는 신뢰성 높은 스트림 처리 가능
  - `대용량 처리에 적합`: 지속적인 고속 이벤트 처리에 Lambda보다 유리
  - 복잡한 처리 가능: 필터링, 변환, 집계, 조인, 이상 탐지 등에 적합


# 데이터 저장소
```
S3 Bucket
├── bronze/
│   └── year=.../month=.../day=.../hour=...
├── silver/
│   └── year=.../month=.../day=.../hour=...
├── flink/
│   └── applications/
│       └── flink-silver-xxxxx.zip
└── errors/
    ├── bronze/
    │   └── ...
    └── silver/
        └── ...

```
# 구조
- 브론즈 유지 및 일부 수정
- 실버 레이어 추가 -> kinesis(bronze)는 공급자 관점, flink는 소비자 관점


# 인프라 수정

| 구분         | 파일              | 변경 내용                                            |
| ---------- | --------------- | ------------------------------------------------ |
| **수정**     | `locals.tf`     | Silver Kinesis/Flink/Firehose 이름 추가              |
| **수정**     | `variables.tf`  | Flink Runtime, Parallelism, Silver Shard 등 변수 추가 |
| **수정**     | `firehose.tf`   | Bronze 오류 경로를 `errors/bronze/`로 정리               |
| **수정**     | `outputs.tf`    | Silver/Flink 관련 Output 추가                        |
| ---------- | --------------- | ------------------------------------------------ |
| **신규**     | `iam-flink.tf`  | Flink + Silver Firehose IAM                      |
| **신규**     | `silver.tf`     | Silver Kinesis + Silver Firehose 생성              |
| **신규**     | `flink.tf`      | Managed Flink + `flink/`에 코드 업로드                 |
| **신규**     | `flink-logs.tf` | Flink CloudWatch 로그                              |

# flink 앱 구성
- 구성
```
flink/
├── app/
│   ├── main.py         : flink 앱 엔트리포인트(실행파트), 브론즈 kinesis 읽기, 
│   │                     transform 모둘 불러서 clean 작업진행, 실버 kinesis 가동된(전처리된) 데이터 전송
│   └── transform.py    : 정제, 전처리 등 데이터 처리 작업 진
├── target/             : 빌드후 생성 : maven 빌드 결과물로 생성
│   └── *.zip           : 빌드후 생성 : 빌드 결과로 생성된  flink 앱
├── assembly/
│   └── assembly.xml    : flink 앱(zip 파일) 성분 구성에 대한 정의 (*.py, pyflink-dependencies.jar)
│
├── application_properties.json : 로컬에서 실행시 input/output kinesis 설정
├── pom.xml             : 의존성 파일들 다운로드, jar 생성, zip 패키징 실행
├── README.md
└── .gitignore
```

- 빌드전 설치 (java, maven)
```
# 윈도우
winget search Microsoft.OpenJDK 
winget install Microsoft.OpenJDK.11
java -version
choco install maven or scoop install main/maven or 직접설치
https://maven.apache.org/download.cgi?utm_source=chatgpt.com 접속 > apache-maven-3.9.16-bin.zip 다운
bin 폴더를 path 설정

# 맥
brew install openjdk@11 maven
export JAVA_HOME=$(/usr/libexec/java_home -v 11)
export PATH="$JAVA_HOME/bin:$PATH"
java -version
mvn -version
```

- 빌드
```
./scripts/build-flink.bat
sh ./scripts/build-flink.sh
```

# 세팅 
```
# 인프라 구성
terraform -chdir=infra fmt
terraform -chdir=infra validate
terraform -chdir=infra plan

./scripts/setup.bat

# Flink 서비스 진입 -> 어플리케이션의 상태 체크 -> 실행 상태가 확인되면 (그린라이트)

# 로그 발송 -> 1분 전후로 s3/버킷/silver 생성 여부 확인 -> 하위에 로그가 존재함 => 완료!!

```

# 확인
- 실시간 스트리미이 데이터 처리 관점
  - 실버 레벨 추가부분
    - flink 앱 코드 확인
      - 추후 필요시 코드 업그레이드(기능 추가 부여)
  - 오염된 데이터 삭제(현재)-> 별도 보관(저장)-> 추후 해당 원인 분석 할 수 있게 보관(확장)
  - 저장데이터 -> Jsonl(gzip)-> parquet저장(glue사용)
  - flink 역할 lambda대체(차이점 이해)
- 실버 -> 골드 추가
  - flink or lambda사용 가능 -> 최종 목표 형태로 가공
  - 중간 과정 동일
  - 최종 S3적재(parquet)/opensearch
- 대시보드
  - s3->athena쿼리 질의, opensearch검색 질의-> 대시보드상 실시간 모니터링 데이터 조회에 응답가능

- 로그생성기 -> Kinesis-> Firehose->S3(bronze)저장
  - batch processing(airflow) + Medalion Architecture
    - 특정 주기 단위로 airflow작동 -> 브론즈-> 실버-> 골드 -> 최종산출물(대시보드, 레포트)구성
- Kafka(뒤에서 체크)
- ELK, EFK
- step function, eventbridge