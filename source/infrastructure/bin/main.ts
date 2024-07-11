/**********************************************************************************************************************
 *  Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.                                                *
 *                                                                                                                    *
 *  Licensed under the Apache License, Version 2.0 (the "License"). You may not use this file except in compliance    *
 *  with the License. A copy of the License is located at                                                             *
 *                                                                                                                    *
 *      http://www.apache.org/licenses/LICENSE-2.0                                                                    *
 *                                                                                                                    *
 *  or in the 'license' file accompanying this file. This file is distributed on an 'AS IS' BASIS, WITHOUT WARRANTIES *
 *  OR CONDITIONS OF ANY KIND, express or implied. See the License for the specific language governing permissions    *
 *  and limitations under the License.                                                                                *
 *********************************************************************************************************************/

import { App, CfnOutput, Stack, StackProps } from "aws-cdk-lib";
import { Construct } from "constructs";
import * as dotenv from "dotenv";
import * as path from "path";

import { ApiConstruct } from "../lib/api/api-stack";
import { ConnectorConstruct } from "../lib/connector/connector-stack";
import { DynamoDBConstruct } from "../lib/db/dynamodb";
import { EtlStack } from "../lib/etl/etl-stack";
import { AssetsConstruct } from "../lib/model/assets-stack";
import { LLMStack } from "../lib/model/llm-stack";
import { BuildConfig } from "../lib/shared/build-config";
import { DeploymentParameters } from "../lib/shared/cdk-parameters";
import { VpcConstruct } from "../lib/shared/vpc-stack";
import { IAMHelper } from "../lib/shared/iam-helper";
import { AOSConstruct } from "../lib/vector-store/os-stack";
import { PortalConstruct } from "../lib/ui/ui-portal";
import { UiExportsConstruct } from "../lib/ui/ui-exports";
import { UserConstruct } from "../lib/user/user-stack";

dotenv.config();

export class RootStack extends Stack {
  constructor(scope: Construct, id: string, props: StackProps = {}) {
    super(scope, id, props);
    this.templateOptions.description = "AI Customer Service";

    this.setBuildConfig();

    const cdkParameters = new DeploymentParameters(this);
    const iamHelper = new IAMHelper(this, "iam-helper");

    const dynamoDBConstruct = new DynamoDBConstruct(this, "ddb");

    const uiPortal = new PortalConstruct(this, "ui");

    const userConstruct = new UserConstruct(this, "auth", {
      adminEmail: cdkParameters.subEmail.valueAsString,
      callbackUrl: uiPortal.portalUrl,
    });

    const apiConstruct = new ApiConstruct(this, "api", {
      // domainEndpoint: "",
      // embeddingAndRerankerEndPoint: "",
      // llmModelId: BuildConfig.LLM_MODEL_ID,
      // instructEndPoint: "",
      sessionTableName: dynamoDBConstruct.sessionTable.tableName,
      messageTableName: dynamoDBConstruct.messageTable.tableName,
      botTableName: dynamoDBConstruct.botTable.tableName,
      userPool: userConstruct.userPool,
      userPoolClientId: userConstruct.oidcClientId,
      iamHelper: iamHelper,
    });


    const uiExports = new UiExportsConstruct(this, "ui-exports", {
      portalBucket: uiPortal.portalBucket,
      uiProps: {
        websocket: apiConstruct.wsEndpoint,
        apiUrl: apiConstruct.apiEndpoint,
        oidcIssuer: userConstruct.oidcIssuer,
        oidcClientId: userConstruct.oidcClientId,
        oidcLogoutUrl: userConstruct.oidcLogoutUrl,
        oidcRedirectUrl: `https://${uiPortal.portalUrl}/signin`,
      },
    });
    uiExports.node.addDependency(uiPortal);


    new CfnOutput(this, "RestAPIEndpoint", {
      value: apiConstruct.apiEndpoint,
    });
    // new CfnOutput(this, "VPC", { value: vpcConstruct.connectorVpc.vpcId });
    new CfnOutput(this, "AdminPortalURL", {
      value: uiPortal.portalUrl,
      description: "admin portal url",
    });
    new CfnOutput(this, "WebSocketAPIEndpoint", {
      value: apiConstruct.wsEndpoint,
    });
    new CfnOutput(this, "OidcClientId", {
      value: userConstruct.oidcClientId,
    });
    new CfnOutput(this, "UserPoolId", {
      value: userConstruct.userPool.userPoolId,
    });
  }

  private setBuildConfig() {
    BuildConfig.DEPLOYMENT_MODE =
      this.node.tryGetContext("DeploymentMode") ?? "ALL";
    BuildConfig.LAYER_PIP_OPTION =
      this.node.tryGetContext("LayerPipOption") ?? "";
    BuildConfig.JOB_PIP_OPTION = this.node.tryGetContext("JobPipOption") ?? "";
    BuildConfig.LLM_MODEL_ID =
      this.node.tryGetContext("LlmModelId") ?? "internlm2-chat-7b";
    BuildConfig.LLM_ENDPOINT_NAME =
      this.node.tryGetContext("LlmEndpointName") ?? "";
  }
}

// For development, use account/region from CDK CLI
const devEnv = {
  account: process.env.CDK_DEFAULT_ACCOUNT,
  region: process.env.CDK_DEFAULT_REGION,
};

const app = new App();
const stackName = app.node.tryGetContext("StackName") || "ai-customer-service";
new RootStack(app, stackName, { env: devEnv });

app.synth();
