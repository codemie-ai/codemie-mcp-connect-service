# codemie-mcp-connect-service

![Version: 0.1.0](https://img.shields.io/badge/Version-0.1.0-informational?style=flat-square) ![Type: application](https://img.shields.io/badge/Type-application-informational?style=flat-square) ![AppVersion: 0.1.0](https://img.shields.io/badge/AppVersion-0.1.0-informational?style=flat-square)

A Helm chart for AI/Run MCP Connect service

**Homepage:** <https://codemie.lab.epam.com>

## Maintainers

| Name | Email | Url |
| ---- | ------ | --- |
| AI/Run | <SpecialEPM-CDMEDevelopmentTeam@epam.com> |  |

## Source Code

* <https://gitbud.epam.com/epm-cdme/codemie-mcp-connect-service.git>

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| affinity | object | `{}` | Assign affinity rules to the statefulset |
| env | list | `[]` | List of extra environment variables to be used by the MCP Connect |
| fullnameOverride | string | `""` |  |
| image.pullPolicy | string | `"IfNotPresent"` | Image pull policy for the MCP Connect |
| image.repository | string | `""` | Repository to use for the MCP Connect |
| image.tag | string | `""` | Tag to use for the MCP Connect. Overrides the image tag whose default is the chart appVersion |
| imagePullSecrets | list | `[]` | Secrets with credentials to pull images from a private registry |
| livenessProbe.failureThreshold | int | `3` | Minimum consecutive failures for the probe to be considered failed after having succeeded |
| livenessProbe.httpGet.path | string | `"/health"` |  |
| livenessProbe.httpGet.port | int | `3000` |  |
| livenessProbe.initialDelaySeconds | int | `20` | Number of seconds after the container has started before probe is initiated |
| livenessProbe.periodSeconds | int | `30` | How often (in seconds) to perform the probe |
| livenessProbe.successThreshold | int | `1` | Minimum consecutive successes for the probe to be considered successful after having failed |
| livenessProbe.timeoutSeconds | int | `1` | Number of seconds after which the probe times out |
| nameOverride | string | `""` |  |
| nodeSelector | object | `{}` | Node selector to be added to the MCP Connect pods |
| podAnnotations | object | `{}` | Annotations to be added to MCP Connect pods |
| podLabels | object | `{}` | Labels to be added to AI/Run MCP Connect pods. |
| podSecurityContext | object | `{}` | Toggle and define pod-level security context |
| readinessProbe.failureThreshold | int | `3` | Minimum consecutive failures for the probe to be considered failed after having succeeded |
| readinessProbe.httpGet.path | string | `"/health"` |  |
| readinessProbe.httpGet.port | int | `3000` |  |
| readinessProbe.initialDelaySeconds | int | `20` | Number of seconds after the container has started before probe is initiated |
| readinessProbe.periodSeconds | int | `30` | How often (in seconds) to perform the probe |
| readinessProbe.successThreshold | int | `1` | Minimum consecutive successes for the probe to be considered successful after having failed |
| readinessProbe.timeoutSeconds | int | `1` | Number of seconds after which the probe times out |
| replicaCount | int | `1` | The number of MCP Connect pods to run |
| resources | object | `{"limits":{"cpu":"500m","memory":"1Gi"},"requests":{"cpu":"100m","memory":"1Gi"}}` | Resource limits and requests for the MCP Connect pods |
| securityContext | object | `{}` | MCP Connect container-level security context |
| service.port | int | `3000` | MCP Connect service port |
| service.type | string | `"ClusterIP"` | MCP Connect service type |
| serviceAccount.annotations | object | `{}` | Annotations applied to created service account |
| serviceAccount.automount | bool | `false` | Automatically mount a ServiceAccount's API credentials? |
| serviceAccount.create | bool | `true` | Specifies whether a service account should be created |
| serviceAccount.name | string | `""` | Service account name for MCP Connect pod If not set and create is true, a name is generated using the fullname template |
| startupProbe.failureThreshold | int | `60` | Minimum consecutive failures for the probe to be considered failed after having succeeded |
| startupProbe.httpGet.path | string | `"/health"` |  |
| startupProbe.httpGet.port | int | `3000` |  |
| startupProbe.initialDelaySeconds | int | `20` | Number of seconds after the container has started before probe is initiated |
| startupProbe.periodSeconds | int | `10` | How often (in seconds) to perform the probe |
| tolerations | list | `[]` | Node selector to be added to the MCP Connect pods |
