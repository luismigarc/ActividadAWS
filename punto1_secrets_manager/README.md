# Punto 1 – AWS Secrets Manager

## Archivos
- `lector_secreto.py`: **el programa**. Solo conoce el *nombre* del secreto; lo lee con Boto3 en tiempo de ejecución (`get_secret_value`, versión `AWSCURRENT`). Tiene una caché opcional en memoria con TTL.
- `secrets_manager.py`: automatiza el ejercicio y guarda la evidencia en `evidencias/punto1/`.
- `politica_lector.json`: política de acceso (plantilla; la real, con el ARN completo, queda en la evidencia).

## Ejecución (WSL)
```bash
uv run python punto1_secrets_manager/secrets_manager.py todo
uv run python punto1_secrets_manager/secrets_manager.py limpiar
# programa suelto (con el rol, antes de limpiar):
uv run python punto1_secrets_manager/lector_secreto.py taller/punto1/db-ficticia --rol <ARN del rol>
```

## Qué demuestra
| Paso | Evidencia |
|---|---|
| Crea `taller/punto1/db-ficticia` (usuario y contraseña ficticios; la contraseña la genera `get_random_password`) y un secreto de control | `secreto_metadatos.json` |
| Rol `taller-ingdata-p1-lector` con permiso **solo** para `GetSecretValue`/`DescribeSecret` sobre el ARN de ese secreto | `politica_acceso.json`, `politica_confianza.json`, `simulacion_politica.csv` |
| El programa asume el rol (STS, credenciales temporales de 15 min), lee el secreto y recibe `AccessDenied` para el secreto de control | `lectura_inicial.json`, `acceso_denegado_control.json` |
| `put_secret_value` crea una versión nueva; el mismo programa, sin cambios, obtiene el valor nuevo (otra huella SHA-256 y otro `VersionId`) | `comparacion_versiones.csv`, `versiones_del_secreto.csv` |
| 50 lecturas sin caché = 50 llamadas cobrables; con caché de 5 min = 1 | `comparacion_cache.csv` |
| Eliminación con `ForceDeleteWithoutRecovery` y verificación | `verificacion_eliminacion.csv` |

La contraseña nunca se imprime: solo su longitud y una huella SHA-256 de 10 caracteres.

## Política de acceso (forma general)
```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"],
    "Resource": "arn:aws:secretsmanager:us-east-1:<cuenta>:secret:taller/punto1/db-ficticia-XXXXXX"
  }]
}
```
Si el secreto usara una clave KMS propia (CMK), además haría falta `kms:Decrypt` sobre esa clave. Con la clave administrada `aws/secretsmanager` no hace falta.
