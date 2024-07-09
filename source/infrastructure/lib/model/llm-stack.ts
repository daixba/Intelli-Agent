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

import * as cdk from "aws-cdk-lib";
import * as iam from "aws-cdk-lib/aws-iam";
import * as sagemaker from "aws-cdk-lib/aws-sagemaker";
import { Construct } from "constructs";
import * as dotenv from "dotenv";

import { BuildConfig } from "../../lib/shared/build-config";
import { IAMHelper } from "../shared/iam-helper";

dotenv.config();

interface LLMStackProps extends cdk.StackProps {
  s3ModelAssets: string;
  embeddingAndRerankerModelPrefix: string;
  embeddingAndRerankerModelVersion: string;
  instructModelPrefix: string;
  instructModelVersion: string;
  iamHelper: IAMHelper;
}

export class LLMStack extends cdk.NestedStack {
  public embeddingAndRerankerEndPoint: string = "";
  public instructEndPoint: string = "";
  private iamHelper: IAMHelper;

  constructor(scope: Construct, id: string, props: LLMStackProps) {
    super(scope, id, props);

    this.iamHelper = props.iamHelper;
    const llmImageUrlDomain =
      this.region === "cn-north-1" || this.region === "cn-northwest-1"
        ? ".amazonaws.com.cn/"
        : ".amazonaws.com/";

    const llmImageUrlAccount =
      this.region === "cn-north-1" || this.region === "cn-northwest-1"
        ? "727897471807.dkr.ecr."
        : "763104351884.dkr.ecr.";

    // Create IAM execution role
    const executionRole = new iam.Role(this, "llmbot-endpoint-execution-role", {
      assumedBy: new iam.ServicePrincipal("sagemaker.amazonaws.com"),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName("AmazonSageMakerFullAccess"),
        iam.ManagedPolicy.fromAwsManagedPolicyName("AmazonS3FullAccess"),
        iam.ManagedPolicy.fromAwsManagedPolicyName("CloudWatchLogsFullAccess"),
      ],
    });
    executionRole.addToPolicy(this.iamHelper.logStatement);
    executionRole.addToPolicy(this.iamHelper.s3Statement);
    executionRole.addToPolicy(this.iamHelper.endpointStatement);
    executionRole.addToPolicy(this.iamHelper.stsStatement);
    executionRole.addToPolicy(this.iamHelper.ecrStatement);
    executionRole.addToPolicy(this.iamHelper.llmStatement);

    console.log(
      "LLM Stack BuildConfig.DEPLOYMENT_MODE: ",
      BuildConfig.DEPLOYMENT_MODE,
    );

    // If Deployment mode is OFFLINE_OPENSEARCH or ALL, then create the following resources
    if (
      BuildConfig.DEPLOYMENT_MODE === "ALL"
    ) {
      // Embedding and Reranker MODEL
      const embeddingAndRerankerModelPrefix = props.embeddingAndRerankerModelPrefix;
      const embeddingAndrerankCodePrefix = embeddingAndRerankerModelPrefix + "_deploy_code";
      const embeddingAndRerankerVersionId = props.embeddingAndRerankerModelVersion;
      const embeddingAndRerankerEndpointName =
        "embedding-and-reranker-" + embeddingAndRerankerModelPrefix + "-" + embeddingAndRerankerVersionId.slice(0, 5);
      // Create model, BucketDeployment construct automatically handles dependencies to ensure model assets uploaded before creating the model in this.region
      const embeddingAndRerankerImageUrl =
        llmImageUrlAccount +
        this.region +
        llmImageUrlDomain +
        "djl-inference:0.21.0-deepspeed0.8.3-cu117";
      const embeddingAndRerankerModel = new sagemaker.CfnModel(this, "embedding-and-reranker-model", {
        executionRoleArn: executionRole.roleArn,
        primaryContainer: {
          image: embeddingAndRerankerImageUrl,
          modelDataUrl: `s3://${props.s3ModelAssets}/${embeddingAndrerankCodePrefix}/`,
          environment: {
            S3_CODE_PREFIX: embeddingAndrerankCodePrefix,
          },
          mode: "MultiModel",
        },
      });

      // Create endpoint configuration, refer to https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_sagemaker.CfnEndpointConfig.html for full options
      const embeddingAndRerankerEndpointConfig = new sagemaker.CfnEndpointConfig(
        this,
        "embedding-and-rerank-endpoint-config",
        {
          productionVariants: [
            {
              initialVariantWeight: 1.0,
              modelName: embeddingAndRerankerModel.attrModelName,
              variantName: "variantProd",
              containerStartupHealthCheckTimeoutInSeconds: 15 * 60,
              initialInstanceCount: 1,
              instanceType: "ml.g4dn.4xlarge",
            },
          ],
        },
      );

      // Create endpoint
      const embeddingAndRerankerTag: cdk.CfnTag = {
        key: "version",
        value: embeddingAndRerankerVersionId,
      };

      const embeddingAndRerankerTagArray = [embeddingAndRerankerTag];

      // Create endpoint
      const embeddingAndRerankerEndpoint = new sagemaker.CfnEndpoint(
        this,
        "embedding-and-reranker-endpoint",
        {
          endpointConfigName: embeddingAndRerankerEndpointConfig.attrEndpointConfigName,
          endpointName: embeddingAndRerankerEndpointName,
          tags: embeddingAndRerankerTagArray,
        },
      );

      this.embeddingAndRerankerEndPoint = embeddingAndRerankerEndpoint.endpointName as string;

    }

    if (BuildConfig.DEPLOYMENT_MODE === "ALL") {
      // INSTRUCT MODEL
      // Create model, BucketDeployment construct automatically handles dependencies to ensure model assets uploaded before creating the model in this.region
      // Instruct MODEL
      // const InstructModelPrefix = props.instructModelPrefix;
      // const InstructCodePrefix = InstructModelPrefix + "_deploy_code";
      // const InstructVersionId = props.instructModelVersion;
      // const InstructEndpointName =
      //   "instruct-" + InstructModelPrefix + "-" + InstructVersionId.slice(0, 5);

      // const instructImageUrl =
      //   llmImageUrlAccount +
      //   this.region +
      //   llmImageUrlDomain +
      //   "djl-inference:0.26.0-deepspeed0.12.6-cu121";
      // const instructModel = new sagemaker.CfnModel(this, "instruct-model", {
      //   executionRoleArn: executionRole.roleArn,
      //   primaryContainer: {
      //     image: instructImageUrl,
      //     modelDataUrl: `s3://${props.s3ModelAssets}/${InstructCodePrefix}/llm_model.tar.gz`,
      //     environment: {
      //       S3_CODE_PREFIX: InstructCodePrefix,
      //     },
      //   },
      // });

      // Create endpoint configuration, refer to https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_sagemaker.CfnEndpointConfig.html for full options
      // const instructEndpointConfig = new sagemaker.CfnEndpointConfig(
      //   this,
      //   "instruct-endpoint-config",
      //   {
      //     productionVariants: [
      //       {
      //         initialVariantWeight: 1.0,
      //         modelName: instructModel.attrModelName,
      //         variantName: "variantProd",
      //         containerStartupHealthCheckTimeoutInSeconds: 15 * 60,
      //         initialInstanceCount: 1,
      //         instanceType: "ml.g5.4xlarge",
      //       },
      //     ],
      //   },
      // );

      // const instructTag: cdk.CfnTag = {
      //   key: "version",
      //   value: InstructVersionId,
      // };

      // const instructTagArray = [instructTag];

      // Create endpoint
      // const InstructEndpoint = new sagemaker.CfnEndpoint(
      //   this,
      //   "instruct-endpoint",
      //   {
      //     endpointConfigName: instructEndpointConfig.attrEndpointConfigName,
      //     endpointName: InstructEndpointName,
      //     tags: instructTagArray,
      //   },
      // );

      // this.instructEndPoint = InstructEndpointName;
      this.instructEndPoint = "instructPlaceHolder";
    }
  }
}
