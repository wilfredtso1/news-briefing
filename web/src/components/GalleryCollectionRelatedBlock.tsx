import React from 'react'
import type { JSX } from 'react/jsx-runtime'

import Img from './Img.tsx'
import BlockHeader from './BlockHeader.tsx'


// Component

        function GalleryCollectionRelatedBlock({
            title,
            subtitle,
            imageId
        }: {
            title: string;
            subtitle: string;
            imageId: string;
        }) {
            return (
                <section className={"Block_block__Q3GQF Block_link__OKLk_ templateGalleryCollectionRelatedBlock_block__RUgwF"}>
                    <div className={"BlockBasic_wrapper__aL_z2 BlockBasic_bottomCenter__msztS"}>
                        <div className={"BlockBasic_header__AjIR3"}>
                            <BlockHeader title={title} subtitle={subtitle} />
                        </div>
                        <div className={"BlockAsset_blockAsset__yO2RP BlockAsset_alignBottom__e80YN"}>
                            <picture className={"BlockAsset_asset__UONUs BlockAsset_bottomCenter__xN9d_"}>
                                <Img id={imageId} />
                            </picture>
                        </div>
                    </div>
                </section>
            );
        }
    

export default GalleryCollectionRelatedBlock
