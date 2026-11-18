#!/bin/sh
# Copyright 2026 EPAM Systems, Inc. ("EPAM")
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Security (EPMCDME-17441): installed as bin/java in JDK 17/21 to disable the Base64 intrinsic
# (CVE-2026-114938, Java4Shell). The real launcher is kept next to it as java.real.
exec "$(dirname "$(readlink -f "$0")")/java.real" -XX:-UseBASE64Intrinsics "$@"
